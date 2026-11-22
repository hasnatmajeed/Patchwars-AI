"""Minimal metadata-only Python upload inspection API."""
import asyncio
import hashlib
import io
import json
import ntpath
import os
import stat
import time
import zlib
import zipfile
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.concurrency import run_in_threadpool

from .scanner import ScanError, ScanTimeout, scan_python
from . import ai_agents
from .verification import verify_patch
from .source_units import MAX_CONTEXT_BYTES, MAX_PREVIEW_BYTES, SourceError, finding_scope, notebook_cells, reconstruct_source
from .patch_ranker import rank_candidates
from .ranker_demo import DemoUnavailable, research_demo

MAX_UPLOAD = 100 * 1024 * 1024
MAX_ZIP_UPLOAD = 500 * 1024 * 1024
MAX_REQUEST = MAX_ZIP_UPLOAD + 256 * 1024
# Fixed upper bounds protect the local machine even if configuration is mistaken.
def budget(name: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(os.environ.get(name, default)), maximum))
    except ValueError:
        return default

MAX_ENTRIES = budget('PATCHWARS_ZIP_ENTRIES', 5000, 10000)
MAX_UNCOMPRESSED = budget('PATCHWARS_ZIP_UNCOMPRESSED', 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024)
MAX_SCAN_SOURCE = budget('PATCHWARS_SCAN_SOURCE_BYTES', 8 * 1024 * 1024, 8 * 1024 * 1024)
MAX_SCAN_TOTAL = budget('PATCHWARS_ZIP_SCAN_BYTES', 128 * 1024 * 1024, 512 * 1024 * 1024)
MAX_CENTRAL_DIRECTORY = 8 * 1024 * 1024
CHUNK = 64 * 1024
PROJECT_TIMEOUT = 120
MAX_FOLLOWUP_CONTEXT_BYTES = 24000

app = FastAPI()


@app.get('/api/research/neural-ranking-demo')
async def neural_ranking_demo() -> dict:
    """Return a clearly separate research demonstration; no hosted provider is used."""
    try:
        return await run_in_threadpool(research_demo)
    except DemoUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


def safe_path(name: str) -> str:
    """Validate an archive-relative path using both Windows and POSIX rules."""
    name = name.replace('\\', '/')
    if not name or name.startswith('/') or ntpath.splitdrive(name)[0]:
        raise HTTPException(400, 'Unsafe path in upload.')
    parts = name.rstrip('/').split('/')
    if any(part in ('', '.', '..') or ':' in part or any(ord(c) < 32 or ord(c) == 127 for c in part) for part in parts):
        raise HTTPException(400, 'Unsafe path in upload.')
    return '/'.join(parts)


class BoundedUploadParser(MultiPartParser):
    """Enforce per-file limits while multipart chunks are being received."""
    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        current = self._current_part.file
        if current is not None:
            self._file_bytes += end - start
            limit = MAX_ZIP_UPLOAD if (current.filename or '').lower().endswith('.zip') else MAX_UPLOAD
            if self._file_bytes > limit:
                raise HTTPException(413, 'Upload too large.')
        super().on_part_data(data, start, end)


def inspect_zip(data) -> tuple[list[str], list[str]]:
    try:
        source = io.BytesIO(data) if isinstance(data, bytes) else data
        source.seek(0)
        end = zipfile._EndRecData(source)
        if not end or end[zipfile._ECD_SIZE] > MAX_CENTRAL_DIRECTORY or end[zipfile._ECD_ENTRIES_TOTAL] > MAX_ENTRIES:
            raise HTTPException(400, 'ZIP central directory exceeds safety limits or is invalid.')
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise HTTPException(400, 'ZIP has too many entries.')
            if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED:
                raise HTTPException(400, 'ZIP uncompressed size limit exceeded.')
            paths = []
            seen = set()
            for entry in entries:
                path = safe_path(entry.filename)
                # Case-insensitive comparison prevents collisions on Windows.
                key = path.casefold()
                if key in seen:
                    raise HTTPException(400, 'ZIP contains duplicate paths.')
                seen.add(key)
                if entry.flag_bits & 1:
                    raise HTTPException(400, 'Encrypted ZIP entries are not supported.')
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise HTTPException(400, 'Unsupported ZIP compression method.')
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise HTTPException(400, 'ZIP symlinks are not supported.')
                mode = entry.external_attr >> 16
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise HTTPException(400, 'Unsupported ZIP entry type.')
                if not entry.is_dir() and path.lower().endswith(('.py', '.ipynb')):
                    paths.append(path)
            return sorted(paths), ([] if paths else ['No Python files found.'])
    except (zipfile.BadZipFile, OSError, ValueError, OverflowError):
        raise HTTPException(400, 'Invalid ZIP archive.') from None


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


async def read_upload(request: Request, allow_member: bool = False):
    # Parse incrementally: Starlette spools file parts to disk beyond 1 MiB.
    if not request.headers.get('content-type', '').lower().startswith('multipart/form-data'):
        raise HTTPException(415, 'Expected multipart form data.')
    async def bounded_stream():
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_REQUEST:
                raise HTTPException(413, 'Upload too large.')
            # Keep parser writes bounded even if the ASGI server supplies a large chunk.
            for offset in range(0, len(chunk), CHUNK):
                yield chunk[offset:offset + CHUNK]

    parser = BoundedUploadParser(request.headers, bounded_stream(), max_files=1,
                                max_fields=4 if allow_member else 0, max_part_size=64 * 1024)
    try:
        form = await parser.parse()
    except BaseException as exc:
        for temporary in parser._files_to_close_on_error:
            temporary.close()
        if isinstance(exc, MultiPartException):
            raise HTTPException(400, 'Invalid multipart upload.') from None
        raise
    try:
        file = form.get('file')
        if not isinstance(file, UploadFile) or not file.filename or len(form.getlist('file')) != 1:
            raise HTTPException(400, 'Provide one file in the file field.')
        if (any(key not in (('file', 'member', 'cell', 'finding_line', 'finding_id') if allow_member else ('file',)) for key, _ in form.multi_items()) or
                len(form.getlist('member')) > 1 or len(form.getlist('cell')) > 1 or
                len(form.getlist('finding_line')) > 1 or len(form.getlist('finding_id')) > 1 or
                (not allow_member and len(form) != 1)):
            raise HTTPException(400, 'Invalid or duplicate upload selection field.')
        member = form.get('member')
        if member is not None and (not isinstance(member, str) or not member):
            raise HTTPException(400, 'Select a Python file from the ZIP.')
        filename = safe_path(file.filename)
        if '/' in filename:
            raise HTTPException(400, 'Invalid upload filename.')
        lower = filename.lower()
        if not lower.endswith(('.py', '.zip', '.ipynb')):
            raise HTTPException(415, 'Only .py, .ipynb and .zip files are supported.')
        await file.seek(0)
        choices = {}
        for key in ('cell', 'finding_line'):
            value = form.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 8:
                    raise HTTPException(400, 'Invalid source selection.')
                choices[key] = int(value)
        finding_id = form.get('finding_id')
        if finding_id is not None:
            if (not isinstance(finding_id, str) or len(finding_id) != 4 or finding_id[0] != 'B'
                    or not finding_id[1:].isascii() or not finding_id[1:].isdigit() or 'finding_line' not in choices):
                raise HTTPException(400, 'Invalid finding selection.')
            choices['finding_id'] = finding_id
        return filename, file, member, choices
    except BaseException:
        await form.close()
        raise


@app.post('/api/inspect')
async def inspect(request: Request) -> dict:
    filename, file, _, _ = await read_upload(request)
    try:
        if filename.lower().endswith(('.py', '.ipynb')):
            paths, warnings, kind = [filename], [], 'python_file'
        else:
            paths, warnings = await run_in_threadpool(inspect_zip, file.file)
            kind = 'zip_project'
        return {'filename': filename, 'upload_type': kind, 'python_file_count': len(paths), 'python_files': paths, 'warnings': warnings}
    finally:
        await file.close()


@app.post('/api/scan')
async def scan(request: Request) -> dict:
    filename, file, _, _ = await read_upload(request)
    return await scan_uploaded(filename, file)


async def scan_uploaded(filename: str, file: UploadFile, progress: Callable[[int, int], None] | None = None) -> dict:
    try:
        if filename.lower().endswith('.zip'):
            return await run_in_threadpool(scan_zip, filename, file.file, progress) if progress else await run_in_threadpool(scan_zip, filename, file.file)
        if filename.lower().endswith('.ipynb'):
            return await run_in_threadpool(scan_notebook, filename, file.file, None, progress) if progress else await run_in_threadpool(scan_notebook, filename, file.file)
        if file.size > MAX_SCAN_SOURCE:
            return {'filename': filename, 'scan_type': 'notebook' if filename.lower().endswith('.ipynb') else 'python_file',
                    'findings': [], 'total_findings': 0, 'scan_status': 'partial',
                    'analyzed_cells': 0, 'eligible_source_files': 1, 'analyzed_source_files': 0,
                    'skipped': [{'path': filename, 'reason': f'Source exceeds the {MAX_SCAN_SOURCE} byte analysis budget.'}]}
        data = await file.read(MAX_SCAN_SOURCE + 1)
        try:
            if progress:
                progress(0, 1)
            findings = await run_in_threadpool(scan_python, data)
        except ScanTimeout:
            raise HTTPException(504, 'Scanner timed out.') from None
        except ScanError:
            raise HTTPException(503, 'Scanner unavailable or unable to analyze file.') from None
        if progress:
            progress(1, 1)
        return {'filename': filename, 'total_findings': len(findings), 'findings': findings, 'scan_status': 'completed'}
    finally:
        await file.close()


@app.post('/api/scan/stream')
async def scan_stream(request: Request) -> StreamingResponse:
    filename, file, _, _ = await read_upload(request)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=16)

    def progress(completed: int, total: int) -> None:
        def offer() -> None:
            if not queue.full():
                queue.put_nowait({'type': 'progress', 'completed': completed, 'total': total})
        loop.call_soon_threadsafe(offer)

    async def events():
        # The task owns the upload until scanning finishes, even on disconnect.
        task = asyncio.create_task(scan_uploaded(filename, file, progress))
        try:
            yield json.dumps({'type': 'stage', 'stage': 'validating'}) + '\n'
            while not task.done() or not queue.empty():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.2)
                    yield json.dumps(item) + '\n'
                except asyncio.TimeoutError:
                    pass
            try:
                result = task.result()
                yield json.dumps({'type': 'result', 'result': result}) + '\n'
            except HTTPException as exc:
                yield json.dumps({'type': 'error', 'message': str(exc.detail), 'status': exc.status_code}) + '\n'
            except Exception:
                yield json.dumps({'type': 'error', 'message': 'Scan could not be completed.', 'status': 500}) + '\n'
        finally:
            if task.done():
                # Retrieve exceptions if the client disconnected before the result.
                if not task.cancelled():
                    task.exception()
            else:
                task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)

    return StreamingResponse(events(), media_type='application/x-ndjson', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@app.post('/api/ai-review')
async def ai_review(request: Request) -> dict:
    return await run_ai_review(request)


async def run_ai_review(request: Request, progress: Callable[[str], Awaitable[None]] | None = None,
                        upload: tuple[str, bytes, str | None, dict] | None = None) -> dict:
    async def emit(stage: str) -> None:
        if progress is not None:
            await progress(stage)

    # Consent is explicit for each request, before any source is sent to a provider.
    if request.headers.get('x-ai-consent', '').strip().lower() != 'true':
        raise HTTPException(400, 'Set X-AI-Consent: true to send this source to the hosted AI provider.')
    refine_header = request.headers.get('x-ai-refine', 'false').strip().lower()
    if refine_header not in ('true', 'false'):
        raise HTTPException(400, 'X-AI-Refine must be true or false.')
    refine = refine_header == 'true'
    await emit('request_accepted')
    filename, file, member, choices = upload if upload is not None else await read_upload(request, allow_member=True)
    try:
        if filename.lower().endswith('.zip'):
            if member is None:
                raise HTTPException(415, 'Select one Python file from the ZIP for review.')
            selected_path, data = await run_in_threadpool(selected_zip_source, file.file, member)
        else:
            if file.size > MAX_SCAN_SOURCE:
                raise HTTPException(413, 'Source exceeds the analysis budget for AI review.')
            data = await file.read(MAX_SCAN_SOURCE + 1)
            selected_path = None
    finally:
        await file.close()
    if not filename.lower().endswith('.zip') and member is not None:
        raise HTTPException(400, 'A ZIP member can only be selected for a ZIP upload.')
    source_name = selected_path or filename
    cell_index = choices.get('cell')
    if source_name.lower().endswith('.ipynb'):
        if cell_index is None:
            raise HTTPException(400, 'Select a notebook code cell for review.')
        try:
            cells = notebook_cells(data)
            cell = next((item for item in cells if item['cell_index'] == cell_index), None)
            if cell is None or cell['reason']:
                raise HTTPException(400, 'Selected notebook cell is unavailable or was not analyzed.')
            data = cell['source'].encode('utf-8')
        except SourceError as exc:
            raise HTTPException(400, str(exc)) from None
    elif cell_index is not None:
        raise HTTPException(400, 'Cell selection requires a notebook.')
    if not data:
        raise HTTPException(400, 'Python source must be nonempty.')
    try:
        source = data.decode('utf-8', errors='strict')
        if not source.strip() or '\x00' in source:
            raise ValueError
    except (UnicodeError, ValueError):
        raise HTTPException(400, 'Python source must be nonempty UTF-8 text.') from None
    if choices.get('finding_line') is None and len(data) > MAX_CONTEXT_BYTES:
        raise HTTPException(413, 'Select a finding for AI review; full source exceeds the 6000-byte context limit.')
    try:
        config = ai_agents.configuration()
    except ai_agents.AIConfigError as exc:
        raise HTTPException(503, str(exc), headers={'X-Review-Category': 'configuration'}) from None
    try:
        before = await run_in_threadpool(scan_python, data)
    except ScanTimeout:
        ai_agents.log_failure('original_scan', 'scanner_timeout')
        raise HTTPException(504, 'Original scan: scanner timed out.', headers={'X-Review-Category': 'scanner_timeout'}) from None
    except ScanError:
        ai_agents.log_failure('original_scan', 'scanner_failure')
        raise HTTPException(503, 'Original scan: scanner unavailable or unable to analyze file.', headers={'X-Review-Category': 'scanner_failure'}) from None
    full_source = source
    selected_line = choices.get('finding_line')
    if selected_line is None and before and before[0].get('test_id') == 'B404':
        selected_line = before[0].get('line_number')
    scope = {'kind': 'cell' if cell_index is not None else 'file', 'start_line': 1,
             'end_line': len(source.splitlines()), 'cell_index': cell_index, 'finding_line': None}
    if selected_line is not None:
        selected_finding = next((item for item in before if item.get('line_number') == selected_line and (not choices.get('finding_id') or item.get('test_id') == choices['finding_id'])), None)
        if selected_finding is None:
            raise HTTPException(400, 'The selected finding was not found in the current scan.')
        try:
            source, start, end = await run_in_threadpool(finding_scope, source, selected_line, selected_finding.get('test_id') == 'B404')
        except SourceError as exc:
            raise HTTPException(413, str(exc)) from None
        before = [dict(item, line_number=item['line_number'] - start + 1) for item in before
                  if start <= item.get('line_number', 0) <= end]
        target_line = selected_line - start + 1
        before.sort(key=lambda item: not (item.get('line_number') == target_line and item.get('test_id') == selected_finding.get('test_id')))
        scope = {'kind': 'finding', 'start_line': start, 'end_line': end,
                 'cell_index': cell_index, 'finding_line': selected_line}
    elif len(data) > MAX_CONTEXT_BYTES:
        raise HTTPException(413, 'Select a finding for AI review; full source exceeds the 6000-byte context limit.')
    if (len(before) > ai_agents.MAX_FINDINGS or
            len(json.dumps(before, ensure_ascii=True).encode('utf-8')) > ai_agents.MAX_FINDINGS_BYTES):
        raise HTTPException(413, 'Too many scanner findings for hosted AI review.')
    if len(json.dumps({'original_code': source, 'bandit_findings': before}, ensure_ascii=True).encode('utf-8')) > 12000:
        raise HTTPException(413, 'Selected AI context and findings exceed the 12000-byte request budget; choose a smaller region.')
    await emit('source_prepared')
    if not before:
        await emit('challenger_started')
        try:
            observation = await asyncio.wait_for(ai_agents.explore(config, source, scoped=scope['kind'] != 'file'), timeout=100)
        except (ai_agents.AIProviderTimeout, asyncio.TimeoutError):
            raise HTTPException(504, 'Exploratory analysis: hosted AI provider timed out.', headers={'X-Review-Category': 'timeout'}) from None
        except ai_agents.AIProviderError as exc:
            raise HTTPException(502, f'Exploratory analysis: {exc}', headers={'X-Review-Category': exc.category}) from None
        await emit('challenger_completed')
        return {'filename': filename, 'selected_file': selected_path, 'scope': scope,
                'review_mode': 'exploratory', 'original_code': source, 'bandit_before': [],
                'exploratory_feedback': observation['feedback'], 'suggested_tests': observation['suggested_tests'],
                'proposed_code': None, 'rounds': [], 'review_status': 'complete', 'review_failure': None,
                'refinement_status': 'not_started_no_findings' if refine else 'not_requested',
                'candidate_selection': 'No patch was requested because no finding was reported.',
                'final_candidate_round': None, 'neural_ranking': {'status': 'no_valid_candidates', 'candidates': []},
                'manual_review_required': True}
    target = before[0]
    await emit('defender_started')
    try:
        patch = await asyncio.wait_for(ai_agents.defender(config, source, before, **({'scoped': True} if scope['kind'] != 'file' else {})), timeout=100)
        try:
            full_patch = reconstruct_source(full_source, source, patch['proposed_code'], scope['start_line'], scope['end_line'])
        except SourceError as exc:
            raise ai_agents.AIProviderError(str(exc), 'invalid_python') from None
    except ai_agents.AIProviderTimeout as exc:
        ai_agents.log_failure('defender_generation', 'timeout')
        raise HTTPException(504, 'Defender generation: hosted AI provider timed out.', headers={'X-Review-Category': exc.category}) from None
    except asyncio.TimeoutError:
        ai_agents.log_failure('defender_generation', 'timeout')
        raise HTTPException(504, 'Defender generation: hosted AI provider timed out.', headers={'X-Review-Category': 'timeout'}) from None
    except ai_agents.AIProviderError as exc:
        ai_agents.log_failure('defender_generation', exc.category)
        raise HTTPException(502, f'Defender generation: {exc}', headers={'X-Review-Category': exc.category}) from None

    await emit('defender_completed')

    def partial_first_round(stage: str, category: str, message: str,
                            after: list[dict] | None) -> dict:
        ai_agents.log_failure(stage, category)
        verification = verify_patch(source, patch['proposed_code'], before, after, target)
        incomplete = {'round': 1, 'round_status': 'partial', 'challenger_status': 'unavailable', 'full_proposed_sha256': hashlib.sha256(full_patch.encode('utf-8')).hexdigest(), 'full_proposed_code': full_patch if len(data) <= MAX_PREVIEW_BYTES else None,
                      'proposed_code': patch['proposed_code'], 'defender_explanation': patch['explanation'],
                      'challenger_feedback': None, 'suggested_tests': None,
                      'bandit_after': after, 'verification': verification}
        return {'filename': filename, 'selected_file': selected_path, 'scope': scope, 'original_code': source, 'full_original_sha256': hashlib.sha256(data).hexdigest(), 'full_original_code': full_source if len(data) <= MAX_PREVIEW_BYTES else None, 'original_findings': before,
                'proposed_code': patch['proposed_code'], 'defender_explanation': patch['explanation'],
                'challenger_feedback': None, 'suggested_tests': None, 'bandit_before': before,
                'bandit_after': after, 'manual_review_required': True, 'verification': verification,
                'rounds': [incomplete], 'final_candidate_round': None,
                'candidate_selection': 'No candidate selected because the first round is incomplete.',
                'review_mode': 'patch', 'target_finding': target,
                'review_status': 'partial', 'review_failure': {'stage': stage, 'category': category, 'message': message},
                'refinement_status': 'not_started' if refine else 'not_requested', 'refinement_error': None,
                'neural_ranking': rank_candidates(source, before, [incomplete])}

    await emit('verification_started')
    try:
        after = await run_in_threadpool(scan_python, patch['proposed_code'].encode('utf-8'))
    except ScanTimeout:
        return partial_first_round('static_verification', 'scanner_timeout',
                                   'Static verification: scanner timed out. Review the proposal manually.', None)
    except ScanError:
        return partial_first_round('static_verification', 'scanner_failure',
                                   'Static verification: scanner could not analyze the proposal.', None)
    verification = verify_patch(source, patch['proposed_code'], before, after, target)
    await emit('verification_completed')
    static_summary = {key: verification.get(key) for key in ('syntax_valid', 'code_changed', 'original_finding_count', 'proposed_finding_count', 'verification_status', 'target_rule_still_reported', 'unrelated_change_possible')}
    if len(json.dumps({'original_code': source, 'proposed_code': patch['proposed_code'], 'bandit_findings': before, 'static_verification': static_summary}, ensure_ascii=True).encode('utf-8')) > MAX_FOLLOWUP_CONTEXT_BYTES:
        return partial_first_round('challenger_review', 'context_limit',
                                   'Challenger context exceeds the 24000-byte budget. Review the proposal manually.', after)
    await emit('challenger_started')
    try:
        review = await asyncio.wait_for(ai_agents.challenger(config, source, patch['proposed_code'], before, verification=static_summary, **({'scoped': True} if scope['kind'] != 'file' else {})), timeout=100)
    except (ai_agents.AIProviderTimeout, asyncio.TimeoutError):
        return partial_first_round('challenger_review', 'timeout',
                                   'Challenger review: hosted AI provider timed out. Try again or review manually.', after)
    except ai_agents.AIProviderError as exc:
        return partial_first_round('challenger_review', exc.category,
                                   f'Challenger review: {exc} Try again or review manually.', after)
    await emit('challenger_completed')
    rounds = [{'round': 1, 'round_status': 'complete', 'challenger_status': 'complete', 'proposed_code': patch['proposed_code'], 'full_proposed_sha256': hashlib.sha256(full_patch.encode('utf-8')).hexdigest(), 'full_proposed_code': full_patch if len(data) <= MAX_PREVIEW_BYTES else None,
               'defender_explanation': patch['explanation'], 'challenger_feedback': review['feedback'],
               'suggested_tests': review['suggested_tests'], 'bandit_after': after,
               'verification': verification}]
    refinement_status = 'not_requested'
    refinement_error = None
    refinement_failure = None
    if refine:
        stage = 'defender_generation'
        try:
            await emit('round2_defender_started')
            summary = {key: verification[key] for key in (
                'syntax_valid', 'verification_status', 'target_rule_still_reported', 'unrelated_change_possible')}
            revised = await asyncio.wait_for(ai_agents.defender(
                config, source, before, patch['proposed_code'], review['feedback'], summary, **({'scoped': True} if scope['kind'] != 'file' else {})), timeout=100)
            try:
                revised_full = reconstruct_source(full_source, source, revised['proposed_code'], scope['start_line'], scope['end_line'])
            except SourceError as exc:
                raise ai_agents.AIProviderError(str(exc), 'invalid_python') from None
            await emit('round2_defender_completed')
            stage = 'static_verification'
            await emit('round2_verification_started')
            revised_after = await run_in_threadpool(scan_python, revised['proposed_code'].encode('utf-8'))
            revised_verification = verify_patch(source, revised['proposed_code'], before, revised_after, target)
            await emit('round2_verification_completed')
            stage = 'challenger_review'
            revised_summary = {key: revised_verification.get(key) for key in ('syntax_valid', 'code_changed', 'original_finding_count', 'proposed_finding_count', 'verification_status', 'target_rule_still_reported', 'unrelated_change_possible')}
            if len(json.dumps({'original_code': source, 'proposed_code': revised['proposed_code'], 'bandit_findings': before, 'static_verification': revised_summary}, ensure_ascii=True).encode('utf-8')) > MAX_FOLLOWUP_CONTEXT_BYTES:
                raise ai_agents.AIProviderError('Challenger context exceeds the 24000-byte budget.', 'context_limit')
            await emit('round2_challenger_started')
            revised_review = await asyncio.wait_for(ai_agents.challenger(
                config, source, revised['proposed_code'], before, verification=revised_summary, **({'scoped': True} if scope['kind'] != 'file' else {})), timeout=100)
            await emit('round2_challenger_completed')
            rounds.append({'round': 2, 'round_status': 'complete', 'challenger_status': 'complete', 'proposed_code': revised['proposed_code'], 'full_proposed_sha256': hashlib.sha256(revised_full.encode('utf-8')).hexdigest(), 'full_proposed_code': revised_full if len(data) <= MAX_PREVIEW_BYTES else None,
                           'defender_explanation': revised['explanation'],
                           'challenger_feedback': revised_review['feedback'],
                           'suggested_tests': revised_review['suggested_tests'],
                           'bandit_after': revised_after, 'verification': revised_verification})
            refinement_status = 'completed'
        except (ScanTimeout, ai_agents.AIProviderTimeout, asyncio.TimeoutError):
            ai_agents.log_failure('round2_' + stage, 'timeout')
            refinement_status, refinement_error = 'partial', f'Second-round {stage.replace("_", " ")}: timed out.'
            refinement_failure = {'stage': stage, 'category': 'timeout', 'message': refinement_error}
        except ScanError:
            ai_agents.log_failure('round2_' + stage, 'scanner_failure')
            refinement_status, refinement_error = 'partial', 'Second-round static verification: scanner could not analyze the proposal.'
            refinement_failure = {'stage': stage, 'category': 'scanner_failure', 'message': refinement_error}
        except ai_agents.AIProviderError as exc:
            ai_agents.log_failure('round2_' + stage, exc.category)
            refinement_status, refinement_error = 'partial', f'Second-round {stage.replace("_", " ")}: {exc}'
            refinement_failure = {'stage': stage, 'category': exc.category, 'message': refinement_error}
    eligible = [r for r in rounds if r['verification']['verification_status'] == 'static_improvement']
    for r in rounds:
        v = r['verification']
        reasons = []
        if not v.get('code_changed'):
            reasons.append('unchanged_from_original')
        if r['round'] > 1 and r['proposed_code'] == rounds[0]['proposed_code']:
            reasons.append('identical_to_round_one')
        if v.get('syntax_valid') is not True:
            reasons.append('invalid_or_unchecked_syntax')
        if r.get('bandit_after') is None:
            reasons.append('static_scan_unavailable')
        if v.get('target_rule_still_reported') is True:
            reasons.append('target_rule_still_reported')
        if v.get('unrelated_change_possible') is True:
            reasons.append('possible_unrelated_change')
        proposal_status = ('unchanged' if not v.get('code_changed') else
                           'duplicate' if r['round'] > 1 and r['proposed_code'] == rounds[0]['proposed_code'] else 'changed')
        r['candidate_assessment'] = {'proposal_status': proposal_status, 'different_from_round_one': r['round'] > 1 and r['proposed_code'] != rounds[0]['proposed_code'],
                                     'ranking_eligible': not reasons, 'reasons': reasons}
    candidate = min(eligible, key=lambda r: (r['verification']['proposed_finding_count'], r['round'])) if eligible else None
    return {'filename': filename, 'selected_file': selected_path, 'scope': scope, 'original_code': source, 'full_original_sha256': hashlib.sha256(data).hexdigest(), 'full_original_code': full_source if len(data) <= MAX_PREVIEW_BYTES else None,
            'original_findings': before, 'proposed_code': patch['proposed_code'],
            'defender_explanation': patch['explanation'], 'challenger_feedback': review['feedback'],
            'suggested_tests': review['suggested_tests'], 'bandit_before': before,
            'bandit_after': after, 'manual_review_required': True,
            'verification': verification, 'rounds': rounds,
            'final_candidate_round': candidate['round'] if candidate else None,
            'candidate_selection': ('Lowest finding count among static improvements; ties favor the earlier round.'
                                    if candidate else 'No candidate met the static improvement criteria.'),
            'review_mode': 'patch', 'target_finding': target,
            'review_status': 'complete', 'review_failure': None,
            'refinement_status': refinement_status, 'refinement_error': refinement_error,
            'refinement_failure': refinement_failure,
            'neural_ranking': rank_candidates(source, before, rounds)}


@app.post('/api/ai-review/stream')
async def ai_review_stream(request: Request) -> StreamingResponse:
    """Stream fixed milestones and one result from the same bounded review pipeline."""
    if request.headers.get('x-ai-consent', '').strip().lower() != 'true':
        async def denied():
            yield json.dumps({'type': 'error', 'category': 'request_error',
                              'message': 'Set X-AI-Consent: true to send this source to the hosted AI provider.'}) + '\n'
        return StreamingResponse(denied(), media_type='application/x-ndjson', headers={'Cache-Control': 'no-store'})
    upload = await read_upload(request, allow_member=True)

    async def events():
        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=8)

        async def progress(stage: str) -> None:
            await queue.put({'type': 'stage', 'stage': stage})

        async def produce() -> None:
            try:
                result = await run_ai_review(request, progress, upload)
                await queue.put({'type': 'result', 'result': result})
            except HTTPException as exc:
                category = (exc.headers or {}).get('X-Review-Category', 'unsupported_input' if exc.status_code == 415 else 'request_error')
                if category not in {'timeout', 'configuration', 'scanner_timeout', 'scanner_failure', 'authentication', 'rate_limit', 'quota_exhausted', 'billing', 'provider_http', 'provider_error', 'provider_request', 'unsupported_input',
                                    'transport_timeout', 'transport_error', 'provider_gateway_timeout',
                                    'empty_response', 'truncated_response', 'invalid_envelope', 'json_parse',
                                    'schema_validation', 'invalid_python', 'unsupported_finish', 'response_too_large'}:
                    category = 'request_error'
                await queue.put({'type': 'error', 'category': category, 'message': exc.detail})
            except Exception:
                await queue.put({'type': 'error', 'category': 'server_error', 'message': 'The review could not be completed.'})
            finally:
                if not asyncio.current_task().cancelling():
                    await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event, ensure_ascii=True, separators=(',', ':')) + '\n'
        finally:
            task.cancel()
            await upload[1].close()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(events(), media_type='application/x-ndjson',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


def selected_zip_source(data, member: str) -> tuple[str, bytes]:
    paths, _ = inspect_zip(data)
    path = safe_path(member)
    if path != member or path not in paths:
        raise HTTPException(400, 'Selected Python file was not found in the ZIP.')
    try:
        with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as archive:
            entry = next(entry for entry in archive.infolist()
                         if not entry.is_dir() and safe_path(entry.filename) == path)
            if entry.file_size > MAX_SCAN_SOURCE:
                raise HTTPException(413, 'Selected source exceeds the analysis budget.')
            with archive.open(entry) as stream:
                source = stream.read(MAX_SCAN_SOURCE + 1)
            if len(source) > MAX_SCAN_SOURCE:
                raise HTTPException(413, 'Selected source exceeds the analysis budget.')
            return path, source
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError, zlib.error, StopIteration):
        raise HTTPException(400, 'Invalid ZIP archive.') from None


class DeadlineReader:
    def __init__(self, stream, deadline: float):
        self.stream = stream
        self.deadline = deadline

    def read(self, size: int = -1):
        if time.monotonic() >= self.deadline:
            raise ScanTimeout('Notebook parse timed out.')
        return self.stream.read(size)

    def seek(self, offset: int, whence: int = 0):
        return self.stream.seek(offset, whence)


def scan_notebook(filename: str, data, deadline: float | None = None, progress: Callable[[int, int], None] | None = None) -> dict:
    deadline = deadline if deadline is not None else time.monotonic() + PROJECT_TIMEOUT
    source = io.BytesIO(data) if isinstance(data, bytes) else data
    try:
        cells = notebook_cells(DeadlineReader(source, deadline), MAX_SCAN_SOURCE)
    except ScanTimeout:
        return {'filename': filename, 'scan_type': 'notebook', 'findings': [], 'total_findings': 0,
                'findings_by_file': {}, 'file_sizes': {}, 'review_targets': {}, 'analyzed_cells': 0,
                'skipped': [{'path': filename, 'reason': 'Notebook parsing exceeded the time budget.'}],
                'scan_status': 'partial'}
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from None
    grouped, sizes, targets, skipped = {}, {}, {}, []
    eligible = sum(1 for cell in cells if not cell['reason'])
    if progress and eligible:
        progress(0, eligible)
    if not cells:
        skipped.append({'path': filename, 'reason': 'Notebook has no code cells to analyze.'})
    for cell in cells:
        label = f'{filename} · cell {cell["cell_index"] + 1}'
        if cell['reason']:
            skipped.append({'path': filename, 'cell_index': cell['cell_index'], 'reason': cell['reason']})
            continue
        remaining = 30 if deadline is None else min(30, deadline - time.monotonic())
        if remaining <= 0:
            skipped.append({'path': filename, 'cell_index': cell['cell_index'], 'reason': 'Project scan time budget exhausted.'})
            continue
        try:
            encoded = cell['source'].encode('utf-8')
            grouped[label] = scan_python(encoded, timeout=remaining)
            sizes[label] = len(encoded)
            targets[label] = {'path': filename, 'cell_index': cell['cell_index']}
            if progress and eligible:
                progress(len(grouped), eligible)
        except ScanTimeout:
            skipped.append({'path': filename, 'cell_index': cell['cell_index'], 'reason': 'Cell scan timed out.'})
        except ScanError:
            skipped.append({'path': filename, 'cell_index': cell['cell_index'], 'reason': 'Cell could not be analyzed.'})
    flat = [dict(finding, file_path=filename, cell_index=targets[label]['cell_index'])
            for label, findings in grouped.items() for finding in findings]
    return {'filename': filename, 'scan_type': 'notebook', 'findings': flat, 'total_findings': len(flat),
            'findings_by_file': grouped, 'file_sizes': sizes, 'review_targets': targets,
            'skipped': skipped, 'analyzed_cells': len(grouped),
            'scan_status': 'partial' if skipped or not grouped else 'completed'}


def zip_progress_workload(data, deadline: float) -> int | None:
    """Count bounded scan units without executing code or retaining notebooks.

    If preflight cannot safely establish a denominator, the scan still runs
    normally and progress remains indeterminate.
    """
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir() and entry.filename.lower().endswith(('.py', '.ipynb'))]
            if sum(entry.file_size for entry in entries) > MAX_SCAN_TOTAL:
                return None
            for entry in entries:
                if time.monotonic() >= deadline:
                    return None
                if entry.filename.lower().endswith('.py'):
                    if entry.file_size <= MAX_SCAN_SOURCE:
                        total += 1
                elif entry.file_size <= MAX_UPLOAD:
                    with archive.open(entry) as stream:
                        cells = notebook_cells(DeadlineReader(stream, deadline), MAX_SCAN_SOURCE)
                    total += sum(1 for cell in cells if not cell['reason'])
        return total or None
    except (SourceError, ScanTimeout, zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError, ValueError, OverflowError, zlib.error):
        return None


def scan_zip(filename: str, data, progress: Callable[[int, int], None] | None = None) -> dict:
    paths, _ = inspect_zip(data)
    if not paths:
        raise HTTPException(400, 'ZIP contains no Python files.')
    progress_total = zip_progress_workload(data, time.monotonic() + 10) if progress else None
    if progress and progress_total:
        progress(0, progress_total)
    deadline = time.monotonic() + PROJECT_TIMEOUT
    grouped = {}
    file_sizes = {}
    targets, skipped = {}, []
    analyzed_files = 0
    completed_units = 0
    total_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as archive:
            for entry in archive.infolist():
                path = safe_path(entry.filename)
                if entry.is_dir():
                    continue
                if not path.lower().endswith(('.py', '.ipynb')):
                    skipped.append({'path': path, 'reason': 'Unsupported file type was not analyzed.'})
                    continue
                if total_bytes + entry.file_size > MAX_SCAN_TOTAL or time.monotonic() >= deadline:
                    skipped.append({'path': path, 'reason': 'Project scan byte or time budget exhausted.'})
                    continue
                if path.lower().endswith('.ipynb'):
                    if entry.file_size > MAX_UPLOAD:
                        skipped.append({'path': path, 'reason': 'Notebook exceeds the 100 MiB per-member limit.'})
                        continue
                    total_bytes += entry.file_size
                    try:
                        with archive.open(entry) as stream:
                            base = completed_units
                            report_cells = (lambda completed, _total: progress(base + completed, progress_total)) if progress and progress_total else None
                            notebook = scan_notebook(path, stream, deadline, report_cells) if report_cells else scan_notebook(path, stream, deadline)
                    except HTTPException as exc:
                        skipped.append({'path': path, 'reason': str(exc.detail)})
                        continue
                    grouped.update(notebook['findings_by_file'])
                    file_sizes.update(notebook['file_sizes'])
                    targets.update(notebook['review_targets'])
                    skipped.extend(notebook['skipped'])
                    completed_units += notebook['analyzed_cells']
                    if notebook['analyzed_cells']:
                        analyzed_files += 1
                    else:
                        skipped.append({'path': path, 'reason': 'No analyzable Python code cells.'})
                    continue
                if entry.file_size > MAX_SCAN_SOURCE:
                    skipped.append({'path': path, 'reason': f'Source exceeds the {MAX_SCAN_SOURCE} byte analysis budget.'})
                    continue
                source = bytearray()
                with archive.open(entry) as stream:
                    while True:
                        if time.monotonic() >= deadline:
                            break
                        chunk = stream.read(CHUNK)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if len(source) + len(chunk) > MAX_SCAN_SOURCE or total_bytes > MAX_SCAN_TOTAL:
                            raise HTTPException(400, 'ZIP decompression budget exceeded.')
                        source.extend(chunk)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    skipped.append({'path': path, 'reason': 'Project scan time budget exhausted.'})
                    continue
                try:
                    grouped[path] = scan_python(bytes(source), timeout=min(30, remaining))
                except ScanTimeout:
                    skipped.append({'path': path, 'reason': 'File scan timed out.'})
                    continue
                except ScanError:
                    skipped.append({'path': path, 'reason': 'File could not be analyzed.'})
                    continue
                file_sizes[path] = len(source)
                targets[path] = {'path': path, 'cell_index': None}
                analyzed_files += 1
                completed_units += 1
                if progress and progress_total:
                    progress(completed_units, progress_total)
        flat = [dict(finding, file_path=targets[label]['path'], **({'cell_index': targets[label]['cell_index']} if targets[label]['cell_index'] is not None else {}))
                for label, findings in grouped.items() for finding in findings]
        return {'filename': filename, 'scan_type': 'zip_project',
                'python_file_count': len(paths), 'eligible_source_files': len(paths), 'analyzed_source_files': analyzed_files,
                'total_findings': len(flat), 'findings': flat, 'findings_by_file': grouped, 'file_sizes': file_sizes,
                'review_targets': targets, 'skipped': skipped, 'scan_status': 'partial' if skipped else 'completed'}
    except ScanTimeout:
        raise HTTPException(504, 'Scanner timed out.') from None
    except ScanError:
        raise HTTPException(503, 'Scanner unavailable or unable to analyze file.') from None
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError, zlib.error):
        raise HTTPException(400, 'Invalid ZIP archive.') from None

"""Minimal metadata-only Python upload inspection API."""
import asyncio
import io
import json
import ntpath
import stat
import time
import zlib
import zipfile

from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool

from .scanner import ScanError, ScanTimeout, scan_python
from . import ai_agents

MAX_UPLOAD = 10 * 1024 * 1024
MAX_REQUEST = MAX_UPLOAD + 64 * 1024  # multipart headers and boundaries
MAX_ENTRIES = 100
MAX_UNCOMPRESSED = 50 * 1024 * 1024
CHUNK = 64 * 1024
PROJECT_TIMEOUT = 120

app = FastAPI()


def safe_path(name: str) -> str:
    """Validate an archive-relative path using both Windows and POSIX rules."""
    name = name.replace('\\', '/')
    if not name or name.startswith('/') or ntpath.splitdrive(name)[0]:
        raise HTTPException(400, 'Unsafe path in upload.')
    parts = name.rstrip('/').split('/')
    if any(part in ('', '.', '..') or ':' in part or any(ord(c) < 32 or ord(c) == 127 for c in part) for part in parts):
        raise HTTPException(400, 'Unsafe path in upload.')
    return '/'.join(parts)


def inspect_zip(data: bytes) -> tuple[list[str], list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
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
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise HTTPException(400, 'ZIP symlinks are not supported.')
                if not entry.is_dir() and path.lower().endswith('.py'):
                    paths.append(path)
            return sorted(paths), ([] if paths else ['No Python files found.'])
    except (zipfile.BadZipFile, OSError, ValueError, OverflowError):
        raise HTTPException(400, 'Invalid ZIP archive.') from None


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


async def read_upload(request: Request, python_only: bool = False) -> tuple[str, bytes]:
    # Bound the whole multipart body before parsing; this also limits non-file fields.
    if not request.headers.get('content-type', '').lower().startswith('multipart/form-data'):
        raise HTTPException(415, 'Expected multipart form data.')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST:
            raise HTTPException(413, 'Upload too large.')
        body.extend(chunk)
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        sent = True
        return {'type': 'http.request', 'body': bytes(body), 'more_body': False}

    bounded_request = Request(request.scope, receive)
    async with bounded_request.form(max_files=1, max_fields=0) as form:
        file = form.get('file')
        if not isinstance(file, UploadFile) or len(form) != 1 or not file.filename:
            raise HTTPException(400, 'Provide one file in the file field.')
        filename = safe_path(file.filename)
        if '/' in filename:
            raise HTTPException(400, 'Invalid upload filename.')
        lower = filename.lower()
        if not (lower.endswith('.py') or lower.endswith('.zip')):
            raise HTTPException(415, 'Only .py and .zip files are supported.')
        if python_only and not lower.endswith('.py'):
            raise HTTPException(415, 'Only .py files are supported for scanning.')
        data = bytearray()
        while chunk := await file.read(CHUNK):
            if len(data) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, 'Upload too large.')
            data.extend(chunk)
        return filename, bytes(data)


@app.post('/api/inspect')
async def inspect(request: Request) -> dict:
        filename, data = await read_upload(request)
        if filename.lower().endswith('.py'):
            paths, warnings, kind = [filename], [], 'python_file'
        else:
            paths, warnings = inspect_zip(bytes(data))
            kind = 'zip_project'
        return {'filename': filename, 'upload_type': kind, 'python_file_count': len(paths), 'python_files': paths, 'warnings': warnings}


@app.post('/api/scan')
async def scan(request: Request) -> dict:
    filename, data = await read_upload(request)
    if filename.lower().endswith('.zip'):
        return await run_in_threadpool(scan_zip, filename, data)
    try:
        findings = await run_in_threadpool(scan_python, data)
    except ScanTimeout:
        raise HTTPException(504, 'Scanner timed out.') from None
    except ScanError:
        raise HTTPException(503, 'Scanner unavailable or unable to analyze file.') from None
    return {'filename': filename, 'total_findings': len(findings), 'findings': findings, 'scan_status': 'completed'}


@app.post('/api/ai-review')
async def ai_review(request: Request) -> dict:
    # Consent is explicit for each request, before any source is sent to a provider.
    if request.headers.get('x-ai-consent', '').strip().lower() != 'true':
        raise HTTPException(400, 'Set X-AI-Consent: true to send this source to the hosted AI provider.')
    filename, data = await read_upload(request, python_only=True)
    if not data or len(data) > ai_agents.MAX_SOURCE_BYTES:
        raise HTTPException(413 if data else 400, 'Python source must be nonempty and no larger than 32 KiB.')
    try:
        source = data.decode('utf-8', errors='strict')
        if not source.strip() or '\x00' in source:
            raise ValueError
    except (UnicodeError, ValueError):
        raise HTTPException(400, 'Python source must be nonempty UTF-8 text.') from None
    try:
        config = ai_agents.configuration()
    except ai_agents.AIConfigError as exc:
        raise HTTPException(503, str(exc)) from None
    try:
        before = await run_in_threadpool(scan_python, data)
        if (len(before) > ai_agents.MAX_FINDINGS or
                len(json.dumps(before, ensure_ascii=True).encode('utf-8')) > ai_agents.MAX_FINDINGS_BYTES):
            raise HTTPException(413, 'Too many scanner findings for hosted AI review.')
        patch = await asyncio.wait_for(ai_agents.defender(config, source, before), timeout=100)
        after = await run_in_threadpool(scan_python, patch['proposed_code'].encode('utf-8'))
        review = await asyncio.wait_for(ai_agents.challenger(config, source, patch['proposed_code'], before), timeout=100)
    except ScanTimeout:
        raise HTTPException(504, 'Scanner timed out.') from None
    except ScanError:
        raise HTTPException(503, 'Scanner unavailable or unable to analyze file.') from None
    except (ai_agents.AIProviderTimeout, asyncio.TimeoutError):
        raise HTTPException(504, 'Hosted AI provider timed out.') from None
    except ai_agents.AIProviderError as exc:
        raise HTTPException(502, str(exc)) from None
    return {'filename': filename, 'original_code': source,
            'original_findings': before, 'proposed_code': patch['proposed_code'],
            'defender_explanation': patch['explanation'], 'challenger_feedback': review['feedback'],
            'suggested_tests': review['suggested_tests'], 'bandit_before': before,
            'bandit_after': after, 'manual_review_required': True}


def scan_zip(filename: str, data: bytes) -> dict:
    paths, _ = inspect_zip(data)
    if not paths:
        raise HTTPException(400, 'ZIP contains no Python files.')
    deadline = time.monotonic() + PROJECT_TIMEOUT
    grouped = {}
    total_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                path = safe_path(entry.filename)
                if entry.is_dir() or not path.lower().endswith('.py'):
                    continue
                source = bytearray()
                with archive.open(entry) as stream:
                    while True:
                        if time.monotonic() >= deadline:
                            raise ScanTimeout('Project scan timed out.')
                        chunk = stream.read(CHUNK)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > MAX_UNCOMPRESSED:
                            raise HTTPException(400, 'ZIP uncompressed size limit exceeded.')
                        source.extend(chunk)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ScanTimeout('Project scan timed out.')
                grouped[path] = scan_python(bytes(source), timeout=min(30, remaining))
        flat = [dict(finding, file_path=path) for path, findings in grouped.items() for finding in findings]
        return {'filename': filename, 'scan_type': 'zip_project',
                'python_file_count': len(grouped), 'total_findings': len(flat),
                'findings': flat, 'findings_by_file': grouped, 'scan_status': 'completed'}
    except ScanTimeout:
        raise HTTPException(504, 'Scanner timed out.') from None
    except ScanError:
        raise HTTPException(503, 'Scanner unavailable or unable to analyze file.') from None
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, NotImplementedError, zlib.error):
        raise HTTPException(400, 'Invalid ZIP archive.') from None

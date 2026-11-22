import io
import asyncio
import json
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import MAX_UPLOAD, MAX_ENTRIES, MAX_UNCOMPRESSED, app

client = TestClient(app)


def upload(name, content):
    return client.post('/api/inspect', files={'file': (name, content, 'application/octet-stream')})


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(('name', 'content', 'total'), [
    ('one.py', b'x = 1\n', 1),
    ('cells.ipynb', json.dumps({'nbformat': 4, 'nbformat_minor': 5, 'metadata': {}, 'cells': [
        {'cell_type': 'code', 'metadata': {}, 'source': ['x = 1\n'], 'outputs': [], 'execution_count': None},
        {'cell_type': 'code', 'metadata': {}, 'source': ['y = 2\n'], 'outputs': [], 'execution_count': None},
    ]}).encode(), 2),
    ('project.zip', make_zip([('a.py', 'x = 1\n'), ('b.py', 'y = 2\n')]), 2),
])
def test_scan_stream_reports_real_completed_units(name, content, total):
    response = client.post('/api/scan/stream', files={'file': (name, content, 'application/octet-stream')})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    values = [(event['completed'], event['total']) for event in events if event['type'] == 'progress']
    assert values[0] == (0, total)
    assert values[-1] == (total, total)
    assert all(a[0] <= b[0] and a[1] == b[1] == total for a, b in zip(values, values[1:]))
    assert events[-1]['type'] == 'result'
    assert events[-1]['result']['scan_status'] == 'completed'


def test_scan_stream_mixed_archive_counts_python_and_notebook_cells():
    notebook = json.dumps({'nbformat': 4, 'nbformat_minor': 5, 'metadata': {}, 'cells': [
        {'cell_type': 'code', 'metadata': {}, 'source': ['x = 1\n'], 'outputs': [], 'execution_count': None},
        {'cell_type': 'code', 'metadata': {}, 'source': ['y = 2\n'], 'outputs': [], 'execution_count': None},
    ]})
    response = client.post('/api/scan/stream', files={'file': ('mixed.zip', make_zip([('a.py', 'x = 1\n'), ('b.ipynb', notebook)]), 'application/zip')})
    events = [json.loads(line) for line in response.text.splitlines()]
    values = [(event['completed'], event['total']) for event in events if event['type'] == 'progress']
    assert values[0] == (0, 3) and values[-1] == (3, 3)
    assert all(a[0] <= b[0] and a[1] == b[1] == 3 for a, b in zip(values, values[1:]))
    assert events[-1]['type'] == 'result' and events[-1]['result']['scan_status'] == 'completed'


def test_scan_stream_mixed_archive_falls_back_when_preflight_unavailable(monkeypatch):
    from backend.app import main
    notebook = json.dumps({'nbformat': 4, 'nbformat_minor': 5, 'metadata': {}, 'cells': [
        {'cell_type': 'code', 'metadata': {}, 'source': ['x = 1\n'], 'outputs': [], 'execution_count': None},
    ]})
    monkeypatch.setattr(main, 'zip_progress_workload', lambda _data, _deadline: None)
    response = client.post('/api/scan/stream', files={'file': ('mixed.zip', make_zip([('a.py', 'x = 1\n'), ('b.ipynb', notebook)]), 'application/zip')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert not any(event['type'] == 'progress' for event in events)
    assert events[-1]['type'] == 'result' and events[-1]['result']['scan_status'] == 'completed'


def test_scan_stream_invalid_notebook_falls_back_and_reports_skip():
    response = client.post('/api/scan/stream', files={'file': ('mixed.zip', make_zip([('a.py', 'x = 1\n'), ('bad.ipynb', '{invalid')]), 'application/zip')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert not any(event['type'] == 'progress' for event in events)
    assert events[-1]['type'] == 'result'
    assert events[-1]['result']['scan_status'] == 'partial'
    assert any(item['path'] == 'bad.ipynb' for item in events[-1]['result']['skipped'])


def test_health():
    assert client.get('/health').json() == {'status': 'ok'}


def test_python_file():
    response = upload('hello.py', b'print(1)')
    assert response.status_code == 200
    assert response.json() == {'filename': 'hello.py', 'upload_type': 'python_file', 'python_file_count': 1, 'python_files': ['hello.py'], 'warnings': []}


def test_zip_project():
    response = upload('project.zip', make_zip([('src\\main.py', 'pass'), ('README.md', 'hello')]))
    assert response.status_code == 200
    assert response.json()['python_files'] == ['src/main.py']
    assert response.json()['upload_type'] == 'zip_project'
    assert response.json()['python_file_count'] == 1


def test_unsupported():
    assert upload('file.txt', b'hello').status_code == 415


def test_corrupt_zip():
    assert upload('bad.zip', b'not a zip').status_code == 400


def test_oversized_upload():
    assert upload('large.py', b'x' * (MAX_UPLOAD + 1)).status_code == 413


def test_python_and_zip_upload_above_previous_limit():
    assert upload('large.py', b'#' * (11 * 1024 * 1024)).status_code == 200
    data = make_zip([('src/a.py', 'pass'), ('padding.bin', b'x' * (11 * 1024 * 1024))])
    assert upload('large.zip', data).status_code == 200


def test_partial_multipart_cancellation_closes_spooled_files(monkeypatch):
    from starlette import formparsers
    from starlette.requests import Request
    from backend.app.main import read_upload
    made = []
    original = formparsers.SpooledTemporaryFile
    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        made.append(file)
        return file
    monkeypatch.setattr(formparsers, 'SpooledTemporaryFile', tracked)
    calls = 0
    async def receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {'type': 'http.request', 'body': b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.py"\r\n\r\n' + b'x' * (1024 * 1024 + 1), 'more_body': True}
        raise asyncio.CancelledError()
    request = Request({'type': 'http', 'method': 'POST', 'headers': [(b'content-type', b'multipart/form-data; boundary=x')]}, receive)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(read_upload(request))
    assert made and all(file.closed for file in made)


@pytest.mark.parametrize('name', ['../escape.py', '..\\escape.py', '/absolute.py', 'C:\\escape.py'])
def test_unsafe_paths(name):
    assert upload('bad.zip', make_zip([(name, 'pass')])).status_code == 400


def test_symlink():
    entry = zipfile.ZipInfo('link.py')
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert upload('bad.zip', make_zip([(entry, 'target')])).status_code == 400


def test_entry_limit():
    assert upload('bad.zip', make_zip([(f'{i}.py', '') for i in range(MAX_ENTRIES + 1)])).status_code == 400


def test_uncompressed_limit():
    # Alter the declared central-directory size without allocating the budget.
    data = bytearray(make_zip([('large.py', '')]))
    pos = data.index(b'PK\x01\x02')
    data[pos + 24:pos + 28] = (MAX_UNCOMPRESSED + 1).to_bytes(4, 'little')
    assert upload('bad.zip', bytes(data)).status_code == 400


def test_duplicate_normalized_paths():
    assert upload('bad.zip', make_zip([('a/b.py', ''), ('a\\b.py', '')])).status_code == 400


def test_empty_project_warning():
    response = upload('empty.zip', make_zip([('readme.txt', '')]))
    assert response.status_code == 200
    assert response.json()['warnings'] == ['No Python files found.']


def scan_upload(name, content):
    return client.post('/api/scan', files={'file': (name, content, 'application/octet-stream')})


def test_demo_fixtures_real_bandit():
    fixtures = Path(__file__).parent / 'fixtures' / 'demo'
    for name, expected in [('clean.py', 0), ('eval_example.py', 1), ('project.zip', 1)]:
        content = (fixtures / name).read_bytes()
        inspected = upload(name, content)
        assert inspected.status_code == 200
        assert inspected.json()['python_file_count'] == (2 if name.endswith('.zip') else 1)
        scanned = scan_upload(name, content)
        assert scanned.status_code == 200
        findings = scanned.json()['findings']
        assert len(findings) == expected
        if findings:
            assert (findings[0]['test_id'], findings[0]['severity'], findings[0]['line_number']) == ('B307', 'MEDIUM', 1)


def test_scan_invalid_uploads():
    assert scan_upload('file.zip', b'not a zip').status_code == 400
    assert scan_upload('../unsafe.py', b'pass').status_code == 400
    assert scan_upload('large.py', b'x' * (MAX_UPLOAD + 1)).status_code == 413


def test_scan_tool_failure(monkeypatch):
    from backend.app import main

    def fail(data):
        raise main.ScanError('private path')

    monkeypatch.setattr(main, 'scan_python', fail)
    response = scan_upload('test.py', b'pass')
    assert response.status_code == 503
    assert 'private path' not in response.text


def test_scan_timeout(monkeypatch):
    from backend.app import main

    def timeout(data):
        raise main.ScanTimeout('private path')

    monkeypatch.setattr(main, 'scan_python', timeout)
    response = scan_upload('test.py', b'pass')
    assert response.status_code == 504
    assert 'private path' not in response.text


def bandit_available():
    import importlib.util
    return importlib.util.find_spec('bandit') is not None


@pytest.mark.skipif(not bandit_available(), reason='Bandit is not installed')
def test_scan_clean_real_bandit():
    response = scan_upload('clean.py', b'def add(a, b):\n    return a + b\n')
    assert response.status_code == 200
    assert response.json() == {'filename': 'clean.py', 'total_findings': 0, 'findings': [], 'scan_status': 'completed'}


@pytest.mark.skipif(not bandit_available(), reason='Bandit is not installed')
def test_scan_eval_real_bandit():
    response = scan_upload('unsafe.py', b'eval(input())\n')
    assert response.status_code == 200
    assert any(item['test_id'] == 'B307' and item['line_number'] == 1 and item['severity'] == 'MEDIUM' for item in response.json()['findings'])


def test_scan_zip_multiple_nested_real_bandit():
    response = scan_upload('project.zip', make_zip([
        ('src/main.py', 'eval(input())\n'),
        ('src/nested/clean.py', 'def add(a, b):\n    return a + b\n'),
        ('README.md', 'ignored'),
    ]))
    assert response.status_code == 200
    result = response.json()
    assert result['scan_type'] == 'zip_project'
    assert result['python_file_count'] == 2
    assert result['scan_status'] == 'partial'
    assert any(item['path'] == 'README.md' for item in result['skipped'])
    assert result['findings_by_file']['src/nested/clean.py'] == []
    assert any(f['test_id'] == 'B307' and f['line_number'] == 1 and f['severity'] == 'MEDIUM' for f in result['findings_by_file']['src/main.py'])
    assert any(f['file_path'] == 'src/main.py' and f['test_id'] == 'B307' for f in result['findings'])
    assert result['total_findings'] == len(result['findings'])


def test_scan_zip_clean_real_bandit():
    response = scan_upload('clean.zip', make_zip([('nested/clean.py', 'x = 1\n')]))
    assert response.status_code == 200
    assert response.json()['total_findings'] == 0
    assert response.json()['findings_by_file'] == {'nested/clean.py': []}


def test_scan_zip_no_python():
    assert scan_upload('empty.zip', make_zip([('readme.txt', '')])).status_code == 400


@pytest.mark.parametrize('name', ['../escape.py', '..\\escape.py', '/a.py', 'C:\\x.py'])
def test_scan_zip_unsafe(name):
    assert scan_upload('bad.zip', make_zip([(name, '')])).status_code == 400


def test_scan_zip_limits():
    assert scan_upload('bad.zip', make_zip([(f'{i}.py', '') for i in range(MAX_ENTRIES + 1)])).status_code == 400
    data = bytearray(make_zip([('large.py', '')]))
    pos = data.index(b'PK\x01\x02')
    data[pos + 24:pos + 28] = (MAX_UNCOMPRESSED + 1).to_bytes(4, 'little')
    assert scan_upload('bad.zip', bytes(data)).status_code == 400
    assert scan_upload('bad.zip', b'x' * (MAX_UPLOAD + 1)).status_code == 400


def test_scan_zip_duplicate():
    assert scan_upload('bad.zip', make_zip([('a/b.py', ''), ('a\\b.py', '')])).status_code == 400


@pytest.mark.parametrize('error,status', [('failure', 503), ('timeout', 504)])
def test_scan_zip_scanner_errors(monkeypatch, error, status):
    from backend.app import main
    def fail(data, timeout):
        raise (main.ScanTimeout('private path') if error == 'timeout' else main.ScanError('private path'))
    monkeypatch.setattr(main, 'scan_python', fail)
    response = scan_upload('test.zip', make_zip([('a.py', 'pass')]))
    assert response.status_code == 200
    assert response.json()['scan_status'] == 'partial'
    assert 'private path' not in response.text


@pytest.mark.parametrize('extension,limit_name', [('.py', 'MAX_UPLOAD'), ('.ipynb', 'MAX_UPLOAD'), ('.zip', 'MAX_ZIP_UPLOAD')])
def test_streaming_file_boundaries_and_cleanup(monkeypatch, extension, limit_name):
    from backend.app import main
    from starlette.requests import Request
    monkeypatch.setattr(main, limit_name, 16)
    async def run(size):
        chunks = [b'--x\r\nContent-Disposition: form-data; name="file"; filename="test' + extension.encode() + b'"\r\n\r\n', b'a' * size, b'\r\n--x--\r\n']
        async def receive():
            chunk = chunks.pop(0)
            return {'type': 'http.request', 'body': chunk, 'more_body': bool(chunks)}
        request = Request({'type': 'http', 'method': 'POST', 'headers': [(b'content-type', b'multipart/form-data; boundary=x')]}, receive)
        return await main.read_upload(request)
    filename, file, _, _ = asyncio.run(run(16))
    assert file.size == 16
    asyncio.run(file.close())
    assert file.file.closed
    with pytest.raises(main.HTTPException) as error:
        asyncio.run(run(17))
    assert error.value.status_code == 413


def test_large_source_is_partial_without_scanning(monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'MAX_SCAN_SOURCE', 4)
    monkeypatch.setattr(main, 'scan_python', lambda *args, **kwargs: pytest.fail('must not scan'))
    for name in ('large.py',):
        result = scan_upload(name, b'12345').json()
        assert result['scan_status'] == 'partial'
        assert result['analyzed_source_files'] == 0
        assert result['skipped'][0]['path'] == name


def test_zip_budget_reports_remaining_sources(monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'MAX_SCAN_TOTAL', 4)
    monkeypatch.setattr(main, 'scan_python', lambda *args, **kwargs: [])
    result = scan_upload('x.zip', make_zip([('a.py', 'pass'), ('b.py', 'pass')])).json()
    assert result['scan_status'] == 'partial'
    assert result['analyzed_source_files'] == 1
    assert result['skipped'][0]['path'] == 'b.py'

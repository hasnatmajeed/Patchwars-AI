import io
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app.main import MAX_UPLOAD, app

client = TestClient(app)


def upload(name, content):
    return client.post('/api/inspect', files={'file': (name, content, 'application/octet-stream')})


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


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


@pytest.mark.parametrize('name', ['../escape.py', '..\\escape.py', '/absolute.py', 'C:\\escape.py'])
def test_unsafe_paths(name):
    assert upload('bad.zip', make_zip([(name, 'pass')])).status_code == 400


def test_symlink():
    entry = zipfile.ZipInfo('link.py')
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert upload('bad.zip', make_zip([(entry, 'target')])).status_code == 400


def test_entry_limit():
    assert upload('bad.zip', make_zip([(f'{i}.py', '') for i in range(101)])).status_code == 400


def test_uncompressed_limit():
    # Alter the declared central-directory size without allocating 50 MiB.
    data = bytearray(make_zip([('large.py', '')]))
    pos = data.index(b'PK\x01\x02')
    data[pos + 24:pos + 28] = (50 * 1024 * 1024 + 1).to_bytes(4, 'little')
    assert upload('bad.zip', bytes(data)).status_code == 400


def test_duplicate_normalized_paths():
    assert upload('bad.zip', make_zip([('a/b.py', ''), ('a\\b.py', '')])).status_code == 400


def test_empty_project_warning():
    response = upload('empty.zip', make_zip([('readme.txt', '')]))
    assert response.status_code == 200
    assert response.json()['warnings'] == ['No Python files found.']


def scan_upload(name, content):
    return client.post('/api/scan', files={'file': (name, content, 'application/octet-stream')})


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
    assert any(item['test_id'] == 'B307' and item['line_number'] == 1 for item in response.json()['findings'])


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
    assert result['scan_status'] == 'completed'
    assert result['findings_by_file']['src/nested/clean.py'] == []
    assert any(f['test_id'] == 'B307' for f in result['findings_by_file']['src/main.py'])
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
    assert scan_upload('bad.zip', make_zip([(f'{i}.py', '') for i in range(101)])).status_code == 400
    data = bytearray(make_zip([('large.py', '')]))
    pos = data.index(b'PK\x01\x02')
    data[pos + 24:pos + 28] = (50 * 1024 * 1024 + 1).to_bytes(4, 'little')
    assert scan_upload('bad.zip', bytes(data)).status_code == 400
    assert scan_upload('bad.zip', b'x' * (MAX_UPLOAD + 1)).status_code == 413


def test_scan_zip_duplicate():
    assert scan_upload('bad.zip', make_zip([('a/b.py', ''), ('a\\b.py', '')])).status_code == 400


@pytest.mark.parametrize('error,status', [('failure', 503), ('timeout', 504)])
def test_scan_zip_scanner_errors(monkeypatch, error, status):
    from backend.app import main
    def fail(data, timeout):
        raise (main.ScanTimeout('private path') if error == 'timeout' else main.ScanError('private path'))
    monkeypatch.setattr(main, 'scan_python', fail)
    response = scan_upload('test.zip', make_zip([('a.py', 'pass')]))
    assert response.status_code == status
    assert 'private path' not in response.text

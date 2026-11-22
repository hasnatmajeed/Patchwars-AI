import io
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app import ai_agents, main

client = TestClient(main.app)


def archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as output:
        for name, content in entries:
            output.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def provider(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    monkeypatch.setattr(main, 'scan_python', lambda data, **kwargs: [{'test_id': 'B307', 'line_number': 1, 'description': data.decode(), 'severity': 'HIGH'}])

    async def defender(config, source, findings, *args):
        calls.append((source, findings, args))
        return {'proposed_code': 'x = 1\n', 'explanation': 'Change.'}

    async def challenger(config, source, proposed, findings, **kwargs):
        return {'feedback': 'Review.', 'suggested_tests': ['Check behavior.']}

    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    return calls


def review(data, member=None, consent=True, refine=False):
    headers = {'X-AI-Consent': 'true'} if consent else {}
    if refine:
        headers['X-AI-Refine'] = 'true'
    return client.post('/api/ai-review', headers=headers,
                       files={'file': ('project.zip', data, 'application/zip')},
                       data={} if member is None else {'member': member})


def test_select_and_switch_files(provider, tmp_path):
    marker = tmp_path / 'never-executed'
    source = f"open({str(marker)!r}, 'w').write('bad')\n"
    data = archive([('a.py', source), ('src/b.py', 'eval(input())\n')])
    scan = client.post('/api/scan', files={'file': ('project.zip', data, 'application/zip')})
    assert scan.status_code == 200
    assert set(scan.json()['findings_by_file']) == {'a.py', 'src/b.py'}
    assert scan.json()['findings_by_file']['a.py'][0]['severity'] == 'HIGH'
    for path, expected in [('a.py', source), ('src/b.py', 'eval(input())\n')]:
        result = review(data, path)
        assert result.status_code == 200
        assert result.json()['selected_file'] == path
        assert provider[-1][0] == expected and provider[-1][1][0]['description'] == expected
    assert not marker.exists()


def test_zip_refinement_and_partial_result(provider, monkeypatch):
    data = archive([('a.py', 'x = 2\n')])
    result = review(data, 'a.py', refine=True)
    assert result.status_code == 200 and result.json()['refinement_status'] == 'completed'
    assert len(provider) == 2 and provider[1][2]

    async def fail(*args, **kwargs):
        raise ai_agents.AIProviderError('Unavailable', 'provider_error')
    monkeypatch.setattr(ai_agents, 'challenger', fail)
    result = review(data, 'a.py')
    assert result.json()['review_status'] == 'partial'
    assert result.json()['selected_file'] == 'a.py' and result.json()['proposed_code']


@pytest.mark.parametrize('member', [None, '../a.py', 'missing.py', 'readme.txt'])
def test_invalid_selection_never_reaches_provider(provider, member):
    result = review(archive([('a.py', 'pass'), ('readme.txt', 'text')]), member)
    assert result.status_code in (400, 415) and not provider


def test_zip_consent_and_size_limits(provider):
    data = archive([('a.py', 'pass')])
    assert review(data, 'a.py', consent=False).status_code == 400
    assert review(archive([('a.py', 'x' * (ai_agents.MAX_SOURCE_BYTES + 1))]), 'a.py').status_code == 413
    assert review(archive([(f'{i}.py', 'x') for i in range(main.MAX_ENTRIES + 1)]), '0.py').status_code == 400
    assert not provider


@pytest.mark.parametrize('entries', [[('../a.py', 'pass')], [('a.py', 'pass'), ('A.py', 'pass')]])
def test_unsafe_archive_rejected_before_provider(provider, entries):
    assert review(archive(entries), 'a.py').status_code == 400
    assert not provider


def test_unsupported_compression_rejected(provider):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2) as output:
        output.writestr('a.py', 'pass')
    assert review(buffer.getvalue(), 'a.py').status_code == 400
    assert not provider


def test_symlink_encryption_and_declared_size_rejected(provider):
    entry = zipfile.ZipInfo('a.py')
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert review(archive([(entry, 'target')]), 'a.py').status_code == 400
    encrypted = bytearray(archive([('a.py', 'pass')]))
    central = encrypted.index(b'PK\x01\x02')
    encrypted[central + 8:central + 10] = (1).to_bytes(2, 'little')
    assert review(bytes(encrypted), 'a.py').status_code == 400
    oversized = bytearray(archive([('a.py', 'pass')]))
    central = oversized.index(b'PK\x01\x02')
    oversized[central + 24:central + 28] = (main.MAX_UNCOMPRESSED + 1).to_bytes(4, 'little')
    assert review(bytes(oversized), 'a.py').status_code == 400
    assert not provider


def test_selected_file_reaches_defender_with_real_bandit(monkeypatch, tmp_path):
    marker = tmp_path / 'not-executed'
    source = f"open({str(marker)!r}, 'w').write('bad')\neval(input())\n"
    captured = []
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))

    async def defender(config, text, findings):
        captured.append((text, findings))
        return {'proposed_code': 'value = input()\n', 'explanation': 'Replace eval.'}

    async def challenger(*args, **kwargs):
        return {'feedback': 'Review behavior.', 'suggested_tests': []}

    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    result = review(archive([('a.py', source), ('other.py', 'unrelated = 1')]), 'a.py')
    assert result.status_code == 200
    assert captured[0][0] == source
    assert any(item['test_id'] == 'B307' for item in captured[0][1])
    assert not marker.exists()

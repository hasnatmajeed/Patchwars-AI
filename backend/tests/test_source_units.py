import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app import ai_agents, main
from backend.app.source_units import MAX_CONTEXT_BYTES, SourceError, finding_scope

client = TestClient(main.app)


def notebook(*cells, language='python'):
    return json.dumps({'cells': list(cells), 'metadata': {'kernelspec': {'language': language}}, 'nbformat': 4}).encode()


def cell(source, kind='code'):
    return {'cell_type': kind, 'source': source, 'outputs': [{'text': 'private output'}]}


def zipped(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path, data in entries:
            archive.writestr(path, data)
    return buffer.getvalue()


def test_notebook_real_bandit_mapping_and_skips(tmp_path):
    marker = tmp_path / 'never-run'
    code = f"open({str(marker)!r}, 'w').write('x')\neval(input())\n"
    data = notebook(cell(['# Markdown'], 'markdown'), cell([code]), cell('%matplotlib inline\n'), cell('!pip install ignored\n'), cell('%%bash\necho no\n'))
    response = client.post('/api/scan', files={'file': ('demo.ipynb', data, 'application/json')})
    assert response.status_code == 200
    result = response.json()
    assert result['scan_status'] == 'partial' and len(result['skipped']) == 3
    assert result['analyzed_cells'] == 1
    assert any(item['test_id'] == 'B307' and item['line_number'] == 2 and item['cell_index'] == 1 for item in result['findings'])
    assert 'private output' not in response.text and not marker.exists()


def test_notebook_bad_json_limits_and_nonpython():
    assert client.post('/api/scan', files={'file': ('bad.ipynb', b'{', 'application/json')}).status_code == 400
    assert client.post('/api/scan', files={'file': ('big.ipynb', b'x' * (10 * 1024 * 1024 + 1), 'application/json')}).status_code == 400
    assert client.post('/api/scan', files={'file': ('many.ipynb', notebook(*(cell('pass') for _ in range(201))), 'application/json')}).status_code == 400
    result = client.post('/api/scan', files={'file': ('r.ipynb', notebook(cell('x=1'), language='R'), 'application/json')}).json()
    assert result['scan_status'] == 'partial' and result['analyzed_cells'] == 0 and result['skipped']


def test_notebook_larger_than_five_mib_is_scanned():
    data = json.dumps({'cells': [cell('x = 1\n')], 'metadata': {'padding': 'x' * (5 * 1024 * 1024)}, 'nbformat': 4}).encode()
    assert 5 * 1024 * 1024 < len(data) < 100 * 1024 * 1024
    response = client.post('/api/scan', files={'file': ('large.ipynb', data, 'application/json')})
    assert response.status_code == 200
    assert response.json()['analyzed_cells'] == 1


def test_mixed_zip_scan_and_traversal():
    data = zipped([('src/app.py', 'eval(input())\n'), ('nested/demo.ipynb', notebook(cell('eval(input())\n'), cell('!ls'))), ('readme.txt', 'text')])
    response = client.post('/api/scan', files={'file': ('project.zip', data, 'application/zip')})
    assert response.status_code == 200
    result = response.json()
    assert result['eligible_source_files'] == result['analyzed_source_files'] == 2
    assert result['scan_status'] == 'partial' and len(result['skipped']) == 2
    assert any(item['file_path'] == 'nested/demo.ipynb' and item['cell_index'] == 0 for item in result['findings'])
    assert client.post('/api/scan', files={'file': ('x.zip', zipped([('../bad.ipynb', notebook(cell('x=1')))]), 'application/zip')}).status_code == 400


def test_large_python_finding_scope_and_consent(monkeypatch, tmp_path):
    marker = tmp_path / 'must-not-run'
    source = ('# padding\n' * 1500 + f'def dangerous(value):\n    open({str(marker)!r}, "w")\n    return eval(value)\n' + 'secret_outside = 4\n').encode()
    line = 1503
    calls = []
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    async def defender(config, code, findings, **kwargs):
        calls.append((code, findings, kwargs))
        return {'proposed_code': 'def dangerous(value):\n    return value\n', 'explanation': 'Replace eval.'}
    async def challenger(config, code, proposed, findings, **kwargs):
        calls.append((code, findings, kwargs))
        return {'feedback': 'Review behavior.', 'suggested_tests': []}
    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    files = {'file': ('large.py', source, 'text/plain')}
    assert client.post('/api/ai-review', files=files, data={'finding_line': str(line)}).status_code == 400
    response = client.post('/api/ai-review', headers={'X-AI-Consent': 'true'}, files=files, data={'finding_line': str(line)})
    assert response.status_code == 200
    result = response.json()
    assert result['scope']['kind'] == 'finding' and result['scope']['start_line'] == 1501 and result['scope']['end_line'] == 1503
    assert len(calls) == 2 and all('secret_outside' not in item[0] and item[2]['scoped'] for item in calls)
    assert any(item['test_id'] == 'B307' and item['line_number'] == 3 for item in calls[0][1])
    assert not marker.exists()
    assert client.post('/api/ai-review', headers={'X-AI-Consent': 'true'}, files=files, data={'finding_line': '1'}).status_code == 400


def test_notebook_zip_cell_review_sends_only_selected_code(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    async def defender(config, source, findings, **kwargs):
        calls.append(source)
        return {'proposed_code': 'x = 1\n', 'explanation': 'change'}
    async def challenger(config, source, proposed, findings, **kwargs):
        return {'feedback': 'review', 'suggested_tests': []}
    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    data = zipped([('nested/n.ipynb', notebook(cell('other = 1\n'), cell('eval(input())\n'), cell('!ls')))])
    result = client.post('/api/ai-review', headers={'X-AI-Consent': 'true'}, files={'file': ('p.zip', data, 'application/zip')}, data={'member': 'nested/n.ipynb', 'cell': '1'})
    assert result.status_code == 200 and result.json()['scope']['cell_index'] == 1
    assert calls == ['eval(input())\n'] and 'private output' not in json.dumps(calls)
    invalid = client.post('/api/ai-review', headers={'X-AI-Consent': 'true'}, files={'file': ('p.zip', data, 'application/zip')}, data={'member': 'nested/n.ipynb', 'cell': '2'})
    assert invalid.status_code == 400


def test_zero_finding_notebook_is_exploratory_even_if_refinement_requested(monkeypatch):
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    async def explore(config, source, **kwargs):
        assert source == 'i = 10\nif i > 15:\n    print("10 is less than 15")\n'
        return {'feedback': 'Check the condition against the intended behavior.', 'suggested_tests': ['Check both branches']}
    async def forbidden(*args, **kwargs):
        pytest.fail('No patch or refinement should be requested without a finding')
    monkeypatch.setattr(ai_agents, 'explore', explore)
    monkeypatch.setattr(ai_agents, 'defender', forbidden)
    monkeypatch.setattr(ai_agents, 'challenger', forbidden)
    data = notebook(cell('i = 10\nif i > 15:\n    print("10 is less than 15")\n'))
    response = client.post('/api/ai-review', headers={'X-AI-Consent': 'true', 'X-AI-Refine': 'true'},
                           files={'file': ('example.ipynb', data, 'application/json')}, data={'cell': '0'})
    assert response.status_code == 200
    result = response.json()
    assert result['review_mode'] == 'exploratory' and result['proposed_code'] is None
    assert result['rounds'] == [] and result['refinement_status'] == 'not_started_no_findings'
    assert result['scope']['cell_index'] == 0


def test_oversized_complete_scope_is_rejected():
    source = 'def huge():\n' + '    x = 1\n' * 1200 + '    return eval(x)\n'
    with pytest.raises(SourceError, match='context limit'):
        finding_scope(source, len(source.splitlines()))
    assert len(source.encode()) > MAX_CONTEXT_BYTES


def test_notebook_scoped_stream_preserves_partial_result(monkeypatch):
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    async def defender(config, source, findings, **kwargs):
        assert kwargs['scoped'] and source == 'value = eval(input())\n'
        return {'proposed_code': 'value = input()\n', 'explanation': 'change'}
    async def challenger(*args, **kwargs):
        raise ai_agents.AIProviderError('Hosted AI response was truncated.', 'truncated_response')
    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    data = notebook(cell('other = 1\nvalue = eval(input())\n'))
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'},
                           files={'file': ('n.ipynb', data, 'application/json')}, data={'cell': '0', 'finding_line': '2'})
    events = [json.loads(line) for line in response.text.splitlines()]
    result = events[-1]['result']
    assert result['review_status'] == 'partial' and result['scope']['start_line'] == 2
    assert result['review_failure']['category'] == 'truncated_response'
    assert result['proposed_code'] == 'value = input()\n'
    assert any(item.get('stage') == 'defender_completed' for item in events)


def test_oversized_followup_context_preserves_defender_without_provider_call(monkeypatch):
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    calls = iter([[{'test_id': 'B307', 'line_number': 1, 'description': 'test finding', 'severity': 'HIGH', 'confidence': 'HIGH'}], []])
    monkeypatch.setattr(main, 'scan_python', lambda data: next(calls, []))
    async def defender(*args, **kwargs):
        return {'proposed_code': 'x = "' + 'a' * 25000 + '"\n', 'explanation': 'change'}
    async def challenger(*args, **kwargs):
        pytest.fail('Oversized context must not reach Challenger')
    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    response = client.post('/api/ai-review', headers={'X-AI-Consent': 'true'},
                           files={'file': ('a.py', b'x=1\n', 'text/plain')})
    assert response.status_code == 200
    assert response.json()['review_status'] == 'partial'
    assert response.json()['review_failure']['category'] == 'context_limit'


def test_large_notebook_output_is_streamed_and_cell_locations_preserved(monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'scan_python', lambda data, **kwargs: [{'line_number': 2, 'test_id': 'B307', 'severity': 'HIGH', 'confidence': 'HIGH', 'description': 'finding'}])
    data = json.dumps({'cells': [cell('notes', 'markdown'), {'cell_type': 'code', 'source': ['x = 1\n', 'eval(input())\n'], 'outputs': [{'data': 'x' * (11 * 1024 * 1024)}]}], 'metadata': {'language_info': {'name': 'python'}}}).encode()
    response = client.post('/api/scan', files={'file': ('large.ipynb', data, 'application/json')})
    assert response.status_code == 200
    result = response.json()
    assert result['scan_status'] == 'completed'
    assert result['findings'][0]['cell_index'] == 1
    assert result['findings'][0]['line_number'] == 2
    response = client.post('/api/scan', files={'file': ('project.zip', zipped([('nested/n.ipynb', data)]), 'application/zip')})
    assert response.status_code == 200
    assert response.json()['findings'][0]['cell_index'] == 1
    assert response.json()['findings'][0]['line_number'] == 2


def test_notebook_oversized_cell_is_skipped_with_index(monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'MAX_SCAN_SOURCE', 10)
    monkeypatch.setattr(main, 'scan_python', lambda *args, **kwargs: [])
    data = notebook(cell('x' * 11), cell('x=1'))
    result = client.post('/api/scan', files={'file': ('n.ipynb', data, 'application/json')}).json()
    assert result['scan_status'] == 'partial'
    assert result['skipped'][0]['cell_index'] == 0
    assert result['analyzed_cells'] == 1


def test_notebook_rejects_excessive_json_nesting():
    data = b'{"cells": [], "extra": ' + b'[' * 130 + b'0' + b']' * 130 + b'}'
    assert client.post('/api/scan', files={'file': ('n.ipynb', data, 'application/json')}).status_code == 400


def test_b404_scope_includes_import_and_related_call():
    source = "import subprocess\n\ndef run():\n    return subprocess.run(['echo', 'safe'])\n"
    scope, start, end = finding_scope(source, 1, True)
    assert start == 1 and end == 4
    assert 'import subprocess' in scope and 'subprocess.run' in scope


def test_b404_import_without_bounded_use_requires_context():
    import pytest
    with pytest.raises(SourceError, match='More code context is needed'):
        finding_scope('import subprocess\n', 1, True)
    source = 'import subprocess\n' + ('# padding\n' * 700) + 'subprocess.run([])\n'
    with pytest.raises(SourceError, match='More code context is needed'):
        finding_scope(source, 1, True)


def test_b404_without_call_never_reaches_provider(monkeypatch):
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    monkeypatch.setattr(main, 'scan_python', lambda *args, **kwargs: [{'test_id': 'B404', 'line_number': 1, 'description': 'import', 'severity': 'LOW'}])
    async def forbidden(*args, **kwargs):
        pytest.fail('Provider must not receive an import-only scope')
    monkeypatch.setattr(ai_agents, 'defender', forbidden)
    response = client.post('/api/ai-review', headers={'X-AI-Consent':'true'}, files={'file':('a.py', b'import subprocess\n', 'text/plain')}, data={'finding_line':'1'})
    assert response.status_code == 413
    assert 'More code context is needed' in response.json()['detail']
    without_selection = client.post('/api/ai-review', headers={'X-AI-Consent':'true'}, files={'file':('a.py', b'import subprocess\n', 'text/plain')})
    assert without_selection.status_code == 413
    assert 'More code context is needed' in without_selection.json()['detail']


def test_selected_rule_disambiguates_findings_on_same_line(monkeypatch):
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    calls = []
    before = [{'test_id':'B404','line_number':1,'description':'import','severity':'LOW'}, {'test_id':'B307','line_number':1,'description':'eval','severity':'HIGH'}]
    def scan(data, **kwargs):
        calls.append(data)
        return before if len(calls) == 1 else []
    monkeypatch.setattr(main, 'scan_python', scan)
    async def defender(config, source, findings, **kwargs):
        assert findings[0]['test_id'] == 'B307'
        return {'proposed_code':'value = input()\n','explanation':'Change.'}
    async def challenger(*args, **kwargs):
        return {'feedback':'Check.','suggested_tests':[]}
    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    response = client.post('/api/ai-review', headers={'X-AI-Consent':'true'}, files={'file':('a.py', b'value = eval(input())\n', 'text/plain')}, data={'finding_line':'1','finding_id':'B307'})
    assert response.status_code == 200
    assert response.json()['target_finding']['test_id'] == 'B307'
    invalid = client.post('/api/ai-review', headers={'X-AI-Consent':'true'}, files={'file':('a.py', b'x=1', 'text/plain')}, data={'finding_line':'1','finding_id':'bad'})
    assert invalid.status_code == 400


def test_reconstruction_preserves_full_file_and_rejects_invalid_context():
    from backend.app.source_units import reconstruct_source, SourceError
    original = 'import os\r\n\r\ndef run():\r\n    return 1\r\n\r\nprint(run())\r\n'
    scope = 'def run():\r\n    return 1\r\n'
    proposed = reconstruct_source(original, scope, 'def run():\n    return 2\n', 3, 4)
    assert proposed == 'import os\r\n\r\ndef run():\n    return 2\n\r\nprint(run())\r\n'
    with pytest.raises(SourceError):
        reconstruct_source(original, 'wrong\n', 'x = 1\n', 3, 4)
    # A valid standalone snippet can still violate the enclosing file's syntax.
    with pytest.raises(SourceError):
        reconstruct_source(original, scope, 'from __future__ import annotations\n', 3, 4)
    with pytest.raises(SourceError):
        reconstruct_source(original, scope, 'def broken(:\n', 3, 4)

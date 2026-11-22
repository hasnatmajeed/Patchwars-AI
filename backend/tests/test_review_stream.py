import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app import ai_agents, main

client = TestClient(main.app)


@pytest.fixture
def mocked_review(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    issue = {'test_id': 'B307', 'line_number': 1, 'description': 'synthetic issue', 'severity': 'HIGH', 'confidence': 'HIGH'}
    monkeypatch.setattr(main, 'scan_python', lambda data, **kwargs: [] if data in (b'x = 2\n', b'x = 3\n') else [issue])

    async def defender(config, source, findings, *args, **kwargs):
        calls.append(('defender', source, args))
        return {'proposed_code': 'x = 2\n', 'explanation': 'A proposal.'}

    async def challenger(config, source, proposed, findings, **kwargs):
        calls.append(('challenger', source))
        return {'feedback': 'Check behavior.', 'suggested_tests': ['Check input.']}

    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    return calls


def stream(data=b'x = 1\n', member=None, consent=True, refine=False, filename='source.py', cell=None, finding_line=None):
    headers = {'X-AI-Consent': 'true'} if consent else {}
    if refine:
        headers['X-AI-Refine'] = 'true'
    fields = {}
    if member is not None:
        fields['member'] = member
    if cell is not None:
        fields['cell'] = str(cell)
    if finding_line is not None:
        fields['finding_line'] = str(finding_line)
    response = client.post('/api/ai-review/stream', headers=headers,
                           files={'file': (filename, data, 'application/octet-stream')}, data=fields)
    return response, [json.loads(line) for line in response.text.splitlines()]


def test_stream_emits_confirmed_milestones_and_result(mocked_review, tmp_path):
    marker = tmp_path / 'not-executed'
    source = f"open({str(marker)!r}, 'w').write('x')\n"
    response, events = stream(source.encode())
    stages = [event['stage'] for event in events if event['type'] == 'stage']
    assert stages == ['request_accepted', 'source_prepared', 'defender_started', 'defender_completed',
                      'verification_started', 'verification_completed', 'challenger_started', 'challenger_completed']
    assert response.headers['cache-control'] == 'no-store'
    assert events[-1]['result']['review_status'] == 'complete'
    assert all(source not in json.dumps(event) and 'x = 2' not in json.dumps(event) for event in events[:-1])
    assert len(mocked_review) == 2 and not marker.exists()


def test_stream_refinement_and_zip_selection(mocked_review):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('a.py', 'first = 1')
        archive.writestr('src/b.py', 'selected = 2')
    _, events = stream(data.getvalue(), member='src/b.py', filename='project.zip', refine=True)
    assert events[-1]['result']['selected_file'] == 'src/b.py'
    assert events[-1]['result']['refinement_status'] == 'completed'
    assert [name for name, *_ in mocked_review] == ['defender', 'challenger', 'defender', 'challenger']
    assert all(call[1] == 'selected = 2' for call in mocked_review)
    assert any(event.get('stage') == 'round2_challenger_completed' for event in events)


def test_stream_partial_challenger_keeps_proposal(mocked_review, monkeypatch):
    async def fail(*args, **kwargs):
        raise ai_agents.AIProviderError('Hosted AI response was truncated.', 'truncated_response')
    monkeypatch.setattr(ai_agents, 'challenger', fail)
    _, events = stream()
    assert events[-1]['result']['review_status'] == 'partial'
    assert events[-1]['result']['review_failure']['category'] == 'truncated_response'
    assert events[-1]['result']['proposed_code'] == 'x = 2\n'
    assert not any(event.get('stage') == 'challenger_completed' for event in events)


def test_stream_second_round_failure_preserves_first(mocked_review, monkeypatch):
    original = ai_agents.defender
    async def fail_second(config, source, findings, *args):
        if args:
            raise ai_agents.AIProviderTimeout('Hosted AI provider timed out.', 'transport_timeout')
        return await original(config, source, findings, *args)
    monkeypatch.setattr(ai_agents, 'defender', fail_second)
    _, events = stream(refine=True)
    assert events[-1]['result']['refinement_status'] == 'partial'
    assert len(events[-1]['result']['rounds']) == 1
    assert events[-1]['result']['neural_ranking']['status'] == 'single_candidate'
    assert not any(event.get('stage') == 'round2_defender_completed' for event in events)


def test_stream_ranking_uses_only_existing_rounds_and_opt_in(mocked_review, monkeypatch):
    async def defender(config, source, findings, *args):
        mocked_review.append(('defender', source, args))
        return {'proposed_code': 'x = 3\n' if args else 'x = 2\n', 'explanation': 'A proposal.'}
    monkeypatch.setattr(ai_agents, 'defender', defender)
    _, first = stream()
    result = first[-1]['result']
    assert result['neural_ranking'] == {'status': 'single_candidate', 'candidates': []}
    assert [c[0] for c in mocked_review] == ['defender', 'challenger']
    mocked_review.clear()
    _, denied = stream(consent=False, refine=True)
    assert denied[-1]['type'] == 'error' and not mocked_review
    _, refined = stream(refine=True)
    result = refined[-1]['result']
    assert result['neural_ranking']['status'] == 'available'
    assert {c['round'] for c in result['neural_ranking']['candidates']} == {1, 2}
    assert len(result['rounds']) == 2 and [c[0] for c in mocked_review] == ['defender', 'challenger', 'defender', 'challenger']
    assert result['final_candidate_round'] in (None, 1)


@pytest.mark.parametrize('in_zip', [False, True])
def test_stream_neural_ranking_for_selected_notebook_cell(mocked_review, in_zip):
    notebook = json.dumps({'cells': [{'cell_type': 'code', 'source': ['x = 1\n']}]}).encode()
    if in_zip:
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('nested/demo.ipynb', notebook)
        payload, filename, member = data.getvalue(), 'project.zip', 'nested/demo.ipynb'
    else:
        payload, filename, member = notebook, 'demo.ipynb', None
    _, events = stream(payload, filename=filename, member=member, cell=0, refine=True)
    result = events[-1]['result']
    assert result['scope']['kind'] == 'cell' and result['scope']['cell_index'] == 0
    assert result['selected_file'] == member
    assert result['neural_ranking']['status'] == 'single_candidate'
    assert result['neural_ranking']['reason'] == 'identical_candidates'


def test_stream_neural_ranking_preserves_selected_finding_scope(mocked_review, monkeypatch):
    finding = {'test_id': 'B307', 'line_number': 2, 'description': 'synthetic', 'severity': 'HIGH', 'confidence': 'HIGH'}
    monkeypatch.setattr(main, 'scan_python', lambda data, **kwargs: [finding] if b'eval' in data else [])
    _, events = stream(b'def parse(s):\n    return eval(s)\n\nx = 1\n', finding_line=2, refine=True)
    result = events[-1]['result']
    assert result['scope']['kind'] == 'finding' and result['scope']['finding_line'] == 2
    assert result['scope']['start_line'] == 1 and result['scope']['end_line'] == 2
    assert result['neural_ranking']['status'] == 'single_candidate'
    assert all('x = 1' not in call[1] for call in mocked_review)


def test_stream_errors_and_consent_are_safe(mocked_review, monkeypatch):
    _, events = stream(consent=False)
    assert events[-1]['type'] == 'error' and not mocked_review
    async def fail(*args):
        raise ai_agents.AIProviderError('Hosted AI authentication or access was rejected.', 'authentication')
    monkeypatch.setattr(ai_agents, 'defender', fail)
    _, events = stream()
    assert events[-1]['type'] == 'error' and events[-1]['category'] == 'authentication'
    assert not any(event.get('stage') == 'defender_completed' for event in events)


def test_stream_defender_timeout_category(mocked_review, monkeypatch):
    async def fail(*args):
        raise ai_agents.AIProviderTimeout('Hosted AI provider timed out.', 'transport_timeout')
    monkeypatch.setattr(ai_agents, 'defender', fail)
    _, events = stream()
    assert events[-1]['category'] == 'transport_timeout'
    assert not any(event.get('stage') == 'defender_completed' for event in events)


def test_stream_static_failure_preserves_proposal(mocked_review, monkeypatch):
    scans = []
    def scan(data, **kwargs):
        scans.append(data)
        if len(scans) == 2:
            raise main.ScanTimeout('internal detail')
        return [{'test_id': 'B307', 'line_number': 1, 'description': 'synthetic issue', 'severity': 'HIGH'}] if len(scans) == 1 else []
    monkeypatch.setattr(main, 'scan_python', scan)
    _, events = stream()
    assert events[-1]['result']['review_status'] == 'partial'
    assert events[-1]['result']['review_failure']['category'] == 'scanner_timeout'
    assert events[-1]['result']['proposed_code'] == 'x = 2\n'
    assert 'internal detail' not in json.dumps(events)
    assert not any(event.get('stage') == 'verification_completed' for event in events)


@pytest.mark.parametrize('kind', ['python', 'notebook', 'zip'])
def test_selected_finding_multipart_contract_for_all_formats(monkeypatch, kind):
    monkeypatch.setattr(ai_agents, 'configuration', lambda: ('url', 'key', 'model'))
    finding = {'test_id':'B311','line_number':18,'description':'random','severity':'LOW','confidence':'HIGH'}
    monkeypatch.setattr(main, 'scan_python', lambda data, **kwargs: [finding] if b'random.random' in data else [])
    calls = []
    async def defender(config, source, findings, **kwargs):
        calls.append((source, findings))
        return {'proposed_code':'value = 1\n','explanation':'Change.'}
    async def challenger(*args, **kwargs):
        return {'feedback':'Check.','suggested_tests':[]}
    monkeypatch.setattr(ai_agents, 'defender', defender)
    monkeypatch.setattr(ai_agents, 'challenger', challenger)
    code = '# comment\n' * 17 + 'value = random.random()\n'
    fields = {'finding_line':'18', 'finding_id':'B311'}
    if kind != 'python':
        notebook = json.dumps({'cells':[{'cell_type':'markdown','source':'notes'} for _ in range(13)] + [{'cell_type':'code','source':code}]}).encode()
        fields['cell'] = '13'
    if kind == 'zip':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive: archive.writestr('nested/demo.ipynb', notebook)
        filename, data = 'project.zip', buffer.getvalue()
        fields['member'] = 'nested/demo.ipynb'
    elif kind == 'notebook':
        filename, data = 'Vitiligo.ipynb', notebook
    else:
        filename, data = 'source.py', code.encode()
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent':'true'}, files={'file':(filename,data,'application/octet-stream')}, data=fields)
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    result = events[-1]['result']
    assert result['target_finding']['test_id'] == 'B311'
    assert result['scope']['finding_line'] == 18
    assert result['scope']['cell_index'] == (13 if kind != 'python' else None)
    assert result['selected_file'] == ('nested/demo.ipynb' if kind == 'zip' else None)
    assert calls and calls[0][1][0]['test_id'] == 'B311'


def test_stream_rejects_missing_multiple_and_unexpected_fields(mocked_review):
    headers = {'X-AI-Consent':'true'}
    missing = client.post('/api/ai-review/stream', headers=headers, files={'other':('a.py',b'pass')})
    assert missing.status_code == 400 and missing.json()['detail'] == 'Provide one file in the file field.'
    multiple = client.post('/api/ai-review/stream', headers=headers, files=[('file',('a.py',b'pass')),('file',('b.py',b'pass'))])
    assert multiple.status_code == 400
    unknown = client.post('/api/ai-review/stream', headers=headers, files={'file':('a.py',b'pass')}, data={'unknown':'1'})
    assert unknown.status_code == 400 and unknown.json()['detail'] == 'Invalid or duplicate upload selection field.'
    assert not mocked_review

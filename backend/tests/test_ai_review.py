import json
from pathlib import Path
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import ai_agents
from backend.app.main import app

client = TestClient(app)


def mock_grounded_scan(monkeypatch):
    """Provider-path tests use one reported issue, followed by clean proposals."""
    from backend.app import main
    calls = []
    def scan(data):
        calls.append(data)
        return [{'test_id': 'B307', 'line_number': 1, 'description': 'synthetic issue', 'severity': 'HIGH', 'confidence': 'HIGH'}] if len(calls) == 1 else []
    monkeypatch.setattr(main, 'scan_python', scan)


@pytest.fixture(autouse=True)
def isolate_local_config(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_agents, 'ENV_PATH', tmp_path / '.env')


def configured(monkeypatch, handler):
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'test-secret')
    monkeypatch.setenv('AI_MODEL', 'test-model')
    original = httpx.AsyncClient
    def make_client(*args, **kwargs):
        return original(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(ai_agents.httpx, 'AsyncClient', make_client)


def reply(content):
    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(content)}}]})


def review(content=b'eval(input())\n', consent=True, name='input.py', refine=False):
    headers = {'X-AI-Consent': 'true'} if consent else {}
    if refine:
        headers['X-AI-Refine'] = 'true'
    return client.post('/api/ai-review', headers=headers, files={'file': (name, content, 'text/plain')})


def test_response_parsers():
    assert ai_agents.parse_defender('{"proposed_code":"x = 1", "explanation":"changed"}')['proposed_code'] == 'x = 1'
    assert ai_agents.parse_challenger('{"feedback":"review", "suggested_tests":["edge"]}')['suggested_tests'] == ['edge']
    for response in ('{}', '{"proposed_code":"if:","explanation":"x"}', '{"proposed_code":"x=1","explanation":1}'):
        with pytest.raises(ai_agents.AIProviderError):
            ai_agents.parse_defender(response)
    for response in ('{}', '{"feedback":"x","suggested_tests":"test"}', '{"feedback":"x","suggested_tests":[null]}'):
        with pytest.raises(ai_agents.AIProviderError):
            ai_agents.parse_challenger(response)


@pytest.mark.parametrize('content', [
    '{"feedback":"review", "suggested_tests":["check"]}',
    '```json\n{"feedback":"review", "suggested_tests":["check"]}\n```',
    'Result follows:\n{"feedback":"review", "suggested_tests":["check"]}\nEnd.',
])
def test_challenger_accepts_unambiguous_json_wrappers(content):
    assert ai_agents.parse_challenger(content) == {'feedback': 'review', 'suggested_tests': ['check']}


def test_defender_accepts_fenced_json():
    assert ai_agents.parse_defender('```json\n{"proposed_code":"x = 1", "explanation":"changed"}\n```')['proposed_code'] == 'x = 1'


@pytest.mark.parametrize('value,category', [
    ('  explanation only  ', 'json_parse'),
    ('{"proposed_code": "unfinished}', 'json_parse'),
    ('{"proposed_code":"x = 1"}', 'schema_validation'),
    ('  ', 'empty_response'),
])
def test_defender_failure_categories(value, category):
    with pytest.raises(ai_agents.AIProviderError) as caught:
        ai_agents.parse_defender(value)
    assert caught.value.category == category


def test_defender_whitespace_and_fenced_json_are_valid():
    assert ai_agents.parse_defender(' \n ```json\n {"proposed_code":"x = 1\\n", "explanation":"change"} \n``` \n')['proposed_code'] == 'x = 1\n'


@pytest.mark.parametrize(('status', 'body', 'category'), [
    (401, 'private marker', 'authentication'), (403, 'private marker', 'authentication'),
    (402, 'private marker', 'billing'), (429, 'rate limited', 'rate_limit'),
    (429, 'insufficient credits', 'quota_exhausted'), (503, 'private marker', 'provider_http'),
])
def test_provider_failure_does_not_repeat_paid_call(monkeypatch, status, body, category):
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(status, text=body)
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'}, files={'file': ('a.py', b'x=1', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['category'] == category
    assert len(calls) == 1
    assert 'private marker' not in response.text


def test_malformed_defender_stops_without_retry(monkeypatch, caplog):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'private_marker {broken'}}]})
        if len(calls) == 2:
            assert 'strictly valid JSON' in payload['messages'][0]['content']
            assert payload['messages'][1] == calls[0]['messages'][1]
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '```json\n{"proposed_code":"x = 1\\n","explanation":"change"}\n```'}}]})
        return reply({'feedback': 'Check behavior.', 'suggested_tests': []})
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'}, files={'file': ('a.py', b'x=2\n', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['category'] == 'json_parse'
    assert [event.get('stage') for event in events].count('defender_completed') == 0
    assert len(calls) == 1 and 'private_marker' not in response.text and 'private_marker' not in caplog.text


@pytest.mark.parametrize('first_status', [200, 503])
def test_defender_failure_stops_after_first_attempt(monkeypatch, first_status):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1 and first_status == 503:
            return httpx.Response(503)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{invalid'}}]})
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'}, files={'file': ('a.py', b'x=1', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert len(calls) == 1 and events[-1]['category'] == ('provider_http' if first_status == 503 else 'json_parse')
    assert not any(event.get('stage') == 'defender_completed' for event in events)


def test_streamed_defender_schema_failure_is_not_retried(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return reply({'proposed_code': 'x = 1\n'})
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'}, files={'file': ('a.py', b'x=1', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert len(calls) == 1 and events[-1]['category'] == 'schema_validation'
    assert not any(event.get('stage') == 'defender_completed' for event in events)


def test_streamed_invalid_python_has_safe_specific_category(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    configured(monkeypatch, lambda request: reply({'proposed_code': 'if:', 'explanation': 'change'}))
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'}, files={'file': ('a.py', b'x=1', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['category'] == 'invalid_python'
    assert 'if:' not in response.text


def test_refinement_prompt_preserves_selected_scope_and_feedback(monkeypatch):
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return reply({'proposed_code': 'def f(x):\n    return x\n', 'explanation': 'Preserve behavior.'})
    configured(monkeypatch, handler)
    config = ('https://provider.example/v1/chat/completions', 'synthetic', 'synthetic')
    original = 'def f(x):\n    return x  # café\n'
    finding = {'test_id': 'B307', 'description': 'Synthetic target.', 'line_number': 2, 'severity': 'HIGH'}
    result = asyncio.run(ai_agents.defender(config, original, [finding, {'test_id': 'B101', 'description': 'Unrelated.'}], 'def f(x):\n    return str(x)\n',
                                           'Avoid changing the return type.', {'syntax_valid': True}, scoped=True))
    payload = captured[0]
    data = json.loads(payload['messages'][1]['content'])
    assert data['original_code'] == original and data['previous_proposal']
    assert data['challenger_feedback'] == 'Avoid changing the return type.'
    assert data['target_finding'] == {key: finding[key] for key in ('test_id', 'description', 'line_number')}
    assert set(data) == {'original_code', 'previous_proposal', 'challenger_feedback', 'target_finding', 'verification_summary'}
    assert 'café' in payload['messages'][1]['content']
    assert 'complete replacement for the supplied original_code only' in payload['messages'][0]['content']
    assert 'one short sentence' in payload['messages'][0]['content']
    assert payload['max_tokens'] == ai_agents.DEFENDER_TOKENS and payload['stream'] is False
    assert result['proposed_code'] == 'def f(x):\n    return x\n'


def test_refinement_prompt_budget_rejects_oversized_request_before_provider(monkeypatch):
    monkeypatch.setattr(ai_agents, 'MAX_REFINEMENT_PROMPT_BYTES', 1000)
    configured(monkeypatch, lambda request: pytest.fail('oversized refinement reached the provider'))
    with pytest.raises(ai_agents.AIProviderError) as error:
        asyncio.run(ai_agents.defender(ai_agents.configuration(), 'x = 1\n', [], 'x = 2\n', 'é' * 500))
    assert error.value.category == 'context_limit'


def test_provider_rejected_model_limits_is_safe_and_not_retried(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(400, text='private provider diagnostic')
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'}, files={'file': ('a.py', b'x=1', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert len(calls) == 1 and events[-1]['category'] == 'provider_request'
    assert 'limits' in events[-1]['message'] and 'private provider diagnostic' not in response.text


def test_challenger_json_failure_preserves_first_proposal(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return reply({'proposed_code': 'x = 1\n', 'explanation': 'change'})
        if len(calls) == 2:
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'not JSON'}}]})
        assert calls[1]['messages'][1] == calls[2]['messages'][1]
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': ' \n```json\n{"feedback":"Check behavior.","suggested_tests":[]}\n``` \n'}}]})
    configured(monkeypatch, handler)
    response = review()
    assert response.status_code == 200 and response.json()['review_status'] == 'partial'
    assert response.json()['challenger_feedback'] is None and len(calls) == 2
    assert response.json()['review_failure']['category'] == 'json_parse'
    assert response.json()['proposed_code'] == 'x = 1\n'


@pytest.mark.parametrize('content', [
    '', '   ', '{"feedback":"unfinished"', '{"feedback":"review"}',
    '{"feedback":"review","suggested_tests":[]} {"feedback":"second","suggested_tests":[]}',
    '{"feedback":"review","feedback":"different","suggested_tests":[]}',
    '{"feedback":"\\ud800","suggested_tests":[]}',
    '{"feedback":"review","suggested_tests":["\\ud800"]}',
    '{"outer":{"feedback":"review","suggested_tests":[]}',
    '[{"feedback":"review","suggested_tests":[]}]',
])
def test_challenger_rejects_empty_ambiguous_or_invalid_output(content):
    with pytest.raises(ai_agents.AIProviderError):
        ai_agents.parse_challenger(content)


@pytest.mark.parametrize('content', [
    '', '```json\n{"proposed_code":"if:","explanation":"bad"}\n```',
    '{"proposed_code":"x = 1"}', '{"proposed_code":"x = 1","explanation":"bad"',
])
def test_defender_rejects_invalid_output(content):
    with pytest.raises(ai_agents.AIProviderError):
        ai_agents.parse_defender(content)


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_temporary_provider_failure_does_not_retry(monkeypatch, status):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(status, text='private error body')
        if len(calls) == 2:
            assert payload['max_tokens'] == ai_agents.DEFENDER_TOKENS
            return reply({'proposed_code': 'x = 1\n', 'explanation': 'change'})
        assert payload['max_tokens'] == ai_agents.CHALLENGER_TOKENS
        return reply({'feedback': 'review', 'suggested_tests': []})
    configured(monkeypatch, handler)
    result = review()
    assert result.status_code == (504 if status == 504 else 502)
    assert len(calls) == 1


@pytest.mark.parametrize('status', [401, 403])
def test_authentication_failure_is_not_retried(monkeypatch, status):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(status, text='private body')
    configured(monkeypatch, handler)
    response = review()
    assert response.status_code == 502 and len(calls) == 1
    assert 'Defender generation' in response.json()['detail']
    assert 'private body' not in response.text


def test_provider_gateway_timeout_is_reported_without_retry(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(504, text='private gateway details')
    configured(monkeypatch, handler)
    response = review()
    assert response.status_code == 504 and len(calls) == 1
    assert 'Defender generation' in response.json()['detail']
    assert 'timed out' in response.json()['detail']
    assert 'private gateway details' not in response.text


@pytest.mark.parametrize('failure', ['timeout', 'empty', 'null', 'truncated', 'malformed'])
def test_challenger_failure_preserves_defender_and_safe_diagnostics(monkeypatch, caplog, failure):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return reply({'proposed_code': 'proposal_marker = 1\n', 'explanation': 'change'})
        if failure == 'timeout':
            raise httpx.ReadTimeout('private timeout details', request=request)
        content = {'empty': '', 'null': None, 'truncated': '{"feedback":',
                   'malformed': 'private_response_marker {"feedback":'}[failure]
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length' if failure == 'truncated' else 'stop',
                                                     'message': {'content': content}}]})
    configured(monkeypatch, handler)
    response = review(b'private_source_marker = 1\n', refine=True)
    assert response.status_code == 200
    result = response.json()
    assert result['review_status'] == 'partial' and result['refinement_status'] == 'not_started'
    assert result['review_failure']['stage'] == 'challenger_review'
    assert result['proposed_code'] == 'proposal_marker = 1\n'
    assert result['challenger_feedback'] is None and result['suggested_tests'] is None
    assert result['rounds'][0]['challenger_status'] == 'unavailable'
    assert result['final_candidate_round'] is None
    assert len(calls) == 2
    assert 'stage=challenger' in caplog.text
    if failure in ('empty', 'null'):
        assert 'empty=True' in caplog.text
    if failure == 'truncated':
        assert 'truncated=True' in caplog.text
    if failure == 'malformed':
        assert 'category=json_parse attempt=1 status=200' in caplog.text
    for secret in ('test-secret', 'private_source_marker', 'proposal_marker', 'private_response_marker', 'private timeout details'):
        assert secret not in caplog.text
    assert 'private_response_marker' not in response.text and 'test-secret' not in response.text


def test_truncated_challenger_preserves_proposal_without_retry(monkeypatch, caplog, tmp_path):
    from backend.app import main
    marker = tmp_path / 'must_not_execute'
    source = f"open({str(marker)!r}, 'w').write('source')\n"
    patch = f"open({str(marker)!r}, 'w').write('patch')\n"
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            return reply({'proposed_code': patch, 'explanation': 'Review change.'})
        if len(calls) == 2:
            return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '{"feedback":'}}]})
        assert len(calls) == 3
        return reply({'feedback': 'Check the remaining risk.', 'suggested_tests': ['Check edge input.']})
    configured(monkeypatch, handler)
    response = review(source.encode())
    result = response.json()
    assert response.status_code == 200 and result['review_status'] == 'partial'
    assert result['challenger_feedback'] is None and result['suggested_tests'] is None
    assert result['review_failure']['category'] == 'truncated_response'
    assert len(calls) == 2 and len(result['rounds']) == 1
    first = json.loads(calls[1]['messages'][1]['content'])
    assert first['original_code'] == source and first['proposed_code'] == patch
    assert calls[1]['max_tokens'] == ai_agents.CHALLENGER_TOKENS
    assert 'stage=challenger category=truncated_response attempt=1 status=200' in caplog.text
    assert 'finish_reason=length' in caplog.text and 'output_bytes=12' in caplog.text
    assert 'test-secret' not in caplog.text and str(marker) not in caplog.text
    assert not marker.exists()


@pytest.mark.parametrize('sequence', [('truncated', 'truncated'), ('transient', 'truncated'), ('truncated', 'transient')])
def test_challenger_attempt_limit_and_partial_preservation(monkeypatch, caplog, sequence):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return reply({'proposed_code': 'x = 1\n', 'explanation': 'change'})
        outcome = sequence[len(calls) - 2]
        if outcome == 'transient':
            return httpx.Response(429, text='private body')
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]})
    configured(monkeypatch, handler)
    response = review(refine=False)
    result = response.json()
    assert response.status_code == 200 and result['review_status'] == 'partial'
    assert result['proposed_code'] == 'x = 1\n'
    assert result['verification']['syntax_valid'] is True
    assert result['challenger_feedback'] is None and result['suggested_tests'] is None
    assert result['final_candidate_round'] is None and len(result['rounds']) == 1
    assert len(calls) == 2
    assert 'private body' not in response.text
    if sequence[0] == 'truncated':
        assert 'empty=True truncated=True' in caplog.text
    else:
        assert result['review_failure']['category'] == 'rate_limit'


def test_refinement_with_first_challenger_truncated_respects_round_limit(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) in (1, 4):
            return reply({'proposed_code': f'x = {len(calls)}\n', 'explanation': 'change'})
        if len(calls) == 2:
            return httpx.Response(200, json={'choices': [{'finish_reason': 'max_tokens', 'message': {'content': ''}}]})
        return reply({'feedback': 'Review behavior.', 'suggested_tests': ['Check input.']})
    configured(monkeypatch, handler)
    response = review(refine=True)
    assert response.status_code == 200
    result = response.json()
    assert result['review_status'] == 'partial' and result['refinement_status'] == 'not_started'
    assert len(result['rounds']) == 1 and result['review_failure']['category'] == 'truncated_response'
    assert len(calls) == 2
    assert [item['max_tokens'] for item in calls] == [ai_agents.DEFENDER_TOKENS, ai_agents.CHALLENGER_TOKENS]


def test_untrusted_finish_reason_is_not_logged(monkeypatch, caplog):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return reply({'proposed_code': 'x = 1\n', 'explanation': 'change'})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'private_finish_marker',
                                                     'message': {'content': '{"feedback":'}}]})
    configured(monkeypatch, handler)
    result = review().json()
    assert result['review_status'] == 'partial' and len(calls) == 2
    assert 'finish_reason=other' in caplog.text and 'output_bytes=12' in caplog.text
    assert 'private_finish_marker' not in caplog.text


def test_defender_truncation_is_not_retried_as_challenger(monkeypatch, caplog):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': ''}}]})
    configured(monkeypatch, handler)
    response = review()
    assert response.status_code == 502 and len(calls) == 1
    assert 'Defender generation' in response.json()['detail']
    assert 'stage=defender category=truncated_response attempt=1' in caplog.text


def test_invalid_envelope_logs_only_safe_metadata(monkeypatch, caplog):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return reply({'proposed_code': 'x = 1\n', 'explanation': 'change'})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                                                     'message': {'content': {'private_marker': 'sensitive'}}}]})
    configured(monkeypatch, handler)
    result = review().json()
    assert result['review_status'] == 'partial' and len(calls) == 2
    assert 'category=invalid_envelope attempt=1 status=200' in caplog.text
    assert 'finish_reason=stop' in caplog.text and 'private_marker' not in caplog.text


def test_consent_config_and_input(monkeypatch):
    for key in ('AI_BASE_URL', 'AI_API_KEY', 'AI_MODEL'):
        monkeypatch.delenv(key, raising=False)
    assert review(consent=False).status_code == 400
    assert review().status_code == 503
    assert review(b'x' * (ai_agents.MAX_SOURCE_BYTES + 1)).status_code == 413
    assert review(b'\xff').status_code == 400
    assert review(b'', name='file.zip').status_code == 415
    monkeypatch.setenv('AI_BASE_URL', 'http://provider.example/v1')
    monkeypatch.setenv('AI_API_KEY', 'key')
    monkeypatch.setenv('AI_MODEL', 'model')
    assert review().status_code == 503


def test_real_bandit_comparison_and_no_code_execution(monkeypatch, tmp_path):
    marker = tmp_path / 'executed.txt'
    source = f"open({str(marker)!r}, 'w').write('executed')\neval(input())\n"
    patch = f"open({str(marker)!r}, 'w').write('executed')\nvalue = input()\n"
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == '/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer test-secret'
        if len(requests) == 1:
            data = json.loads(body['messages'][1]['content'])
            assert data['original_code'] == source
            assert any(f['test_id'] == 'B307' for f in data['bandit_findings'])
            return reply({'proposed_code': patch, 'explanation': 'Replace eval.'})
        assert json.loads(body['messages'][1]['content'])['proposed_code'] == patch
        return reply({'feedback': 'Check compatibility.', 'suggested_tests': ['Check input behavior.']})
    configured(monkeypatch, handler)
    response = review(source.encode())
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(requests) == 2
    assert result['original_code'] == source and result['proposed_code'] == patch
    assert result['original_findings'] == result['bandit_before']
    assert any(item['test_id'] == 'B307' for item in result['bandit_before'])
    assert not any(item['test_id'] == 'B307' for item in result['bandit_after'])
    assert result['suggested_tests'] == ['Check input behavior.']
    assert result['challenger_feedback'] == 'Check compatibility.'
    assert result['manual_review_required'] is True
    assert result['refinement_status'] == 'not_requested' and len(result['rounds']) == 1
    verification = result['verification']
    assert verification['syntax_valid'] is True
    assert verification['verification_status'] == 'static_improvement'
    assert verification['original_finding_count'] == len(result['bandit_before'])
    assert verification['proposed_finding_count'] == len(result['bandit_after'])
    assert verification['manual_review_required'] is True
    assert not marker.exists()
    assert 'test-secret' not in response.text


def test_refinement_two_rounds(monkeypatch, tmp_path):
    from backend.app import main
    marker = tmp_path / 'marker'
    source = f"open({str(marker)!r}, 'w').write('x')\neval(input())\n"
    first = 'value = input()\n'
    second = 'value = str(input())\n'
    finding = {'test_id': 'B307', 'line_number': 2, 'description': 'eval', 'severity': 'MEDIUM', 'confidence': 'HIGH'}
    scans = []
    def scan(data):
        scans.append(data)
        return [finding] if len(scans) == 1 else []
    monkeypatch.setattr(main, 'scan_python', scan)
    calls = []
    def handler(request):
        data = json.loads(json.loads(request.content)['messages'][1]['content'])
        calls.append(data)
        if len(calls) == 1:
            assert data['original_code'] == source and data['bandit_findings'] == [finding]
            assert data['repair_objective']['issue_id'] == 'B307' and data['repair_objective']['line_number'] == 2
            return reply({'proposed_code': first, 'explanation': 'first'})
        if len(calls) == 2:
            assert data['proposed_code'] == first
            assert data['repair_objective']['issue_id'] == 'B307'
            assert data['static_verification']['verification_status'] == 'no_static_improvement'
            return reply({'feedback': 'Review input.', 'suggested_tests': ['test one']})
        if len(calls) == 3:
            assert data['original_code'] == source
            assert data['target_finding'] == {'test_id': 'B307', 'line_number': 2, 'description': 'eval'}
            assert data['previous_proposal'] == first and data['challenger_feedback'] == 'Review input.'
            assert data['verification_summary']['verification_status'] == 'no_static_improvement'
            return reply({'proposed_code': second, 'explanation': 'second'})
        assert len(calls) == 4 and data['proposed_code'] == second and data['original_code'] == source
        return reply({'feedback': 'Review revised.', 'suggested_tests': ['test two']})
    configured(monkeypatch, handler)
    result = review(source.encode(), refine=True).json()
    assert len(calls) == 4 and len(scans) == 3
    assert result['refinement_status'] == 'completed' and result['refinement_error'] is None
    assert [r['proposed_code'] for r in result['rounds']] == [first, second]
    assert result['proposed_code'] == first and result['challenger_feedback'] == 'Review input.'
    assert result['rounds'][1]['challenger_feedback'] == 'Review revised.'
    assert result['final_candidate_round'] is None
    assert result['rounds'][0]['verification']['unrelated_change_possible'] is True
    assert result['original_code'] == source and not marker.exists()


@pytest.mark.parametrize('failure,category,attempts', [
    ('invalid_json', 'json_parse', 1),
    ('missing_fields', 'schema_validation', 1),
    ('invalid_python', 'invalid_python', 1),
    ('truncated', 'truncated_response', 1),
    ('connection_closed', 'transport_error', 1),
])
def test_refinement_output_failures_are_distinct_and_preserve_round_one(monkeypatch, caplog, failure, category, attempts):
    from backend.app import main
    import hashlib
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return reply({'proposed_code': 'x = 2\n', 'explanation': 'First patch.'})
        if len(calls) == 2:
            return reply({'feedback': 'Check input behavior.', 'suggested_tests': ['Check input.']})
        if failure == 'invalid_json':
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{broken'}}]})
        if failure == 'missing_fields':
            return reply({'proposed_code': 'x = 3\n'})
        if failure == 'invalid_python':
            return reply({'proposed_code': 'if:', 'explanation': 'Invalid.'})
        if failure == 'connection_closed':
            raise httpx.RemoteProtocolError('Private provider diagnostic.', request=request)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '{'}}]})
    configured(monkeypatch, handler)
    result = review(b'x = 1\n', refine=True).json()
    assert len(calls) == 2 + attempts
    assert result['refinement_status'] == 'partial' and result['refinement_failure']['category'] == category
    assert result['rounds'][0]['proposed_code'] == 'x = 2\n' and len(result['rounds']) == 1
    assert result['full_original_sha256'] == hashlib.sha256(b'x = 1\n').hexdigest()
    assert result['rounds'][0]['full_proposed_sha256'] == hashlib.sha256(b'x = 2\n').hexdigest()
    assert result['neural_ranking']['status'] == 'single_candidate'
    assert f'stage=round2_defender_generation category={category}' in caplog.text
    assert 'x = 1' not in caplog.text and 'test-secret' not in caplog.text


@pytest.mark.parametrize(('finish_metadata', 'content'), [
    ({'finish_reason': 'length'}, '{'),
    ({'native_finish_reason': 'max_tokens'}, '{"proposed_code":"x = 3\\n","explanation":"Looks complete."}'),
])
def test_refinement_truncation_preserves_round_one_without_retry(monkeypatch, caplog, finish_metadata, content):
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return reply({'proposed_code': 'x = 2\n', 'explanation': 'First.'})
        if len(calls) == 2:
            return reply({'feedback': 'Keep input behavior.', 'suggested_tests': []})
        if len(calls) == 3:
            data = json.loads(payload['messages'][1]['content'])
            assert data['original_code'] == 'x = 1\n' and data['previous_proposal'] == 'x = 2\n'
            assert data['challenger_feedback'] == 'Keep input behavior.'
            assert data['target_finding']['test_id'] == 'B307'
            assert set(data['verification_summary']) == {'syntax_valid', 'verification_status', 'target_rule_still_reported', 'unrelated_change_possible'}
            return httpx.Response(200, json={'choices': [{**finish_metadata, 'message': {'content': content}}],
                                             'usage': {'prompt_tokens': 238, 'completion_tokens': 8192,
                                                       'completion_tokens_details': {'reasoning_tokens': 8000}}})
        pytest.fail('truncated refinement was retried or sent to the Challenger')
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true', 'X-AI-Refine': 'true'},
                           files={'file': ('input.py', b'x = 1\n', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    result = events[-1]['result']
    assert len(calls) == 3 and result['refinement_status'] == 'partial'
    assert not any(event.get('stage') in ('round2_defender_completed', 'round2_challenger_started') for event in events)
    assert [r['proposed_code'] for r in result['rounds']] == ['x = 2\n']
    assert result['refinement_failure']['category'] == 'truncated_response'
    assert 'truncated' in result['refinement_failure']['message']
    assert result['neural_ranking']['status'] == 'single_candidate'
    assert 'stage=round2_defender_generation max_tokens=8192 prompt_bytes=' in caplog.text
    assert 'prompt_tokens=238 completion_tokens=8192 reasoning_tokens=8000' in caplog.text
    assert 'Looks complete' not in caplog.text and 'Keep input behavior' not in caplog.text


def test_refinement_selects_fewer_remaining_findings(monkeypatch):
    from backend.app import main
    first = {'test_id': 'B101', 'line_number': 1, 'description': 'one'}
    second = {'test_id': 'B102', 'line_number': 2, 'description': 'two'}
    outputs = iter([[first, second], [first], []])
    monkeypatch.setattr(main, 'scan_python', lambda data: next(outputs))
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) in (1, 3):
            return reply({'proposed_code': f'x = {len(calls)}\n', 'explanation': 'patch'})
        return reply({'feedback': 'review', 'suggested_tests': []})
    configured(monkeypatch, handler)
    result = review(refine=True).json()
    assert result['refinement_status'] == 'completed'
    assert result['final_candidate_round'] == 2
    assert result['proposed_code'] == result['rounds'][0]['proposed_code']


@pytest.mark.parametrize('failure', ['provider', 'quota', 'invalid_patch', 'challenger', 'scanner', 'scanner_timeout'])
def test_refinement_failure_keeps_first_round(monkeypatch, failure):
    from backend.app import main
    scans = []
    def scan(data):
        scans.append(data)
        if len(scans) == 3 and failure in ('scanner', 'scanner_timeout'):
            raise main.ScanTimeout('private') if failure == 'scanner_timeout' else main.ScanError('private')
        return [{'test_id': 'B307', 'line_number': 1, 'description': 'synthetic issue', 'severity': 'HIGH'}] if len(scans) == 1 else []
    monkeypatch.setattr(main, 'scan_python', scan)
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 2:
            return reply({'feedback': 'first review', 'suggested_tests': []})
        if len(calls) == 3 and failure == 'provider':
            return httpx.Response(401)
        if len(calls) == 3 and failure == 'quota':
            return httpx.Response(429, text='insufficient_quota')
        if len(calls) == 3 and failure == 'invalid_patch':
            return reply({'proposed_code': 'if:', 'explanation': 'bad'})
        if len(calls) == 4:
            return reply({'feedback': '', 'suggested_tests': []})
        return reply({'proposed_code': 'x = 1\n', 'explanation': 'patch'})
    configured(monkeypatch, handler)
    response = review(refine=True)
    assert response.status_code == 200
    result = response.json()
    assert result['refinement_status'] == 'partial' and len(result['rounds']) == 1
    assert result['challenger_feedback'] == 'first review' and result['refinement_error']
    if failure == 'quota':
        assert result['refinement_failure']['category'] == 'quota_exhausted'
        assert len(calls) == 3
    assert result['final_candidate_round'] == 1
    assert 'private' not in response.text and len(calls) <= 4


def test_refinement_requires_consent_and_valid_header(monkeypatch):
    assert review(consent=False, refine=True).status_code == 400
    response = client.post('/api/ai-review', headers={'X-AI-Consent': 'true', 'X-AI-Refine': '2'},
                           files={'file': ('a.py', b'x=1', 'text/plain')})
    assert response.status_code == 400


@pytest.mark.parametrize('failure,status', [('timeout', 504), ('error', 503)])
@pytest.mark.parametrize('failure_at', [1, 2])
def test_review_scanner_failure_preserves_api_errors(monkeypatch, failure, status, failure_at):
    from backend.app import main
    calls = []
    def scan(data):
        calls.append(data)
        if len(calls) == failure_at:
            raise main.ScanTimeout('private') if failure == 'timeout' else main.ScanError('private')
        return [{'test_id': 'B307', 'line_number': 1, 'description': 'synthetic issue', 'severity': 'HIGH'}] if len(calls) == 1 else []
    monkeypatch.setattr(main, 'scan_python', scan)
    configured(monkeypatch, lambda request: reply({'proposed_code': 'x = 1\n', 'explanation': 'change'}))
    response = review()
    if failure_at == 1:
        assert response.status_code == status
        assert 'Original scan' in response.json()['detail']
    else:
        assert response.status_code == 200
        result = response.json()
        assert result['review_status'] == 'partial'
        assert result['review_failure']['stage'] == 'static_verification'
        assert result['proposed_code'] == 'x = 1\n'
        assert result['bandit_after'] is None
        assert result['verification']['verification_status'] == 'verification_incomplete'
        assert result['challenger_feedback'] is None and result['suggested_tests'] is None
    assert 'private' not in response.text


def test_provider_failure_and_timeout_do_not_retry(monkeypatch):
    attempts = []
    def failure(request):
        attempts.append(1)
        return httpx.Response(503, text='sensitive internal error')
    configured(monkeypatch, failure)
    response = review()
    assert response.status_code == 502 and len(attempts) == 1
    assert 'sensitive' not in response.text and 'test-secret' not in response.text
    attempts.clear()
    def timeout(request):
        attempts.append(1)
        raise httpx.ReadTimeout('private detail', request=request)
    # Replace transport factory without wrapping the already monkeypatched class.
    monkeypatch.undo()
    configured(monkeypatch, timeout)
    response = review()
    assert response.status_code == 504 and len(attempts) == 1
    assert 'private detail' not in response.text


def test_provider_invalid_response(monkeypatch):
    configured(monkeypatch, lambda request: reply({'proposed_code': 'if:', 'explanation': 'bad'}))
    response = review()
    assert response.status_code == 502
    assert 'traceback' not in response.text.lower()


def test_invalid_challenger_is_rejected(monkeypatch):
    attempts = []
    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return reply({'proposed_code': 'value = 1\n', 'explanation': 'Change.'})
        return reply({'feedback': 'review', 'suggested_tests': 'not a list'})
    configured(monkeypatch, handler)
    response = review()
    assert response.status_code == 200 and len(attempts) == 2
    result = response.json()
    assert result['review_status'] == 'partial'
    assert result['review_failure']['stage'] == 'challenger_review'
    assert result['review_failure']['category'] == 'schema_validation'
    assert result['challenger_feedback'] is None and result['suggested_tests'] is None
    assert result['proposed_code'] == 'value = 1\n'


def test_oversized_provider_reply_rejected(monkeypatch):
    configured(monkeypatch, lambda request: httpx.Response(200, content=b'x' * (ai_agents.MAX_RESPONSE_BYTES + 1)))
    assert review().status_code == 502


def test_openrouter_configuration_accepts_free_model(monkeypatch):
    monkeypatch.setenv('AI_BASE_URL', 'https://openrouter.ai/api/v1')
    monkeypatch.setenv('AI_API_KEY', 'fake-regression-key')
    monkeypatch.setenv('AI_MODEL', 'qwen/qwen3-coder:free')
    url, _, model = ai_agents.configuration()
    assert url == 'https://openrouter.ai/api/v1/chat/completions'
    assert model == 'qwen/qwen3-coder:free'


@pytest.mark.parametrize('variable,value,expected', [
    ('AI_BASE_URL', '', 'AI_BASE_URL'),
    ('AI_BASE_URL', 'http://example.test/v1', 'AI_BASE_URL'),
    ('AI_BASE_URL', 'https://example.test/v1?query=1', 'AI_BASE_URL'),
    ('AI_BASE_URL', 'https://name:secret@example.test/v1', 'AI_BASE_URL'),
    ('AI_API_KEY', '', 'AI_API_KEY'),
    ('AI_API_KEY', 'fake\nkey', 'AI_API_KEY'),
    ('AI_MODEL', '', 'AI_MODEL'),
    ('AI_MODEL', 'bad\nmodel', 'AI_MODEL'),
])
def test_safe_config_errors(monkeypatch, variable, value, expected):
    monkeypatch.setenv('AI_BASE_URL', 'https://openrouter.ai/api/v1')
    monkeypatch.setenv('AI_API_KEY', 'fake-private-value')
    monkeypatch.setenv('AI_MODEL', 'qwen/qwen3-coder:free')
    monkeypatch.setenv(variable, value)
    response = review()
    assert response.status_code == 503
    assert expected in response.json()['detail']
    assert 'fake-private-value' not in response.text
    assert 'name:secret' not in response.text


@pytest.mark.parametrize('status,expected', [(401, 'authentication'), (403, 'authentication'), (429, 'rate limit'), (500, 'provider returned an error')])
def test_provider_errors_are_distinct_and_do_not_echo_body(monkeypatch, status, expected):
    configured(monkeypatch, lambda request: httpx.Response(status, text='sensitive-provider-detail'))
    response = review()
    assert response.status_code == 502
    assert expected in response.json()['detail'].lower()
    assert 'sensitive-provider-detail' not in response.text
    assert 'test-secret' not in response.text


@pytest.mark.parametrize('status,body,category,attempts', [
    (429, 'insufficient_quota private-marker', 'quota_exhausted', 1),
    (429, 'rate limited private-marker', 'rate_limit', 1),
    (402, 'private-marker', 'billing', 1),
    (401, 'private-marker', 'authentication', 1),
    (403, 'private-marker', 'authentication', 1),
])
def test_safe_streamed_provider_error_categories(monkeypatch, caplog, status, body, category, attempts):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(status, text=body)
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review/stream', headers={'X-AI-Consent': 'true'},
                           files={'file': ('a.py', b'x=1', 'text/plain')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['category'] == category and len(calls) == attempts
    assert 'private-marker' not in response.text and 'private-marker' not in caplog.text
    assert 'test-secret' not in response.text and 'test-secret' not in caplog.text


def test_quota_failure_after_defender_preserves_proposal(monkeypatch):
    from backend.app import main
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        calls.append(1)
        return reply({'proposed_code': 'x = 1\n', 'explanation': 'change'}) if len(calls) == 1 else httpx.Response(429, text='insufficient credits')
    configured(monkeypatch, handler)
    result = review().json()
    assert result['review_status'] == 'partial' and result['review_failure']['category'] == 'quota_exhausted'
    assert result['proposed_code'] == 'x = 1\n' and len(calls) == 2


def test_network_error_is_distinct(monkeypatch):
    def fail(request):
        raise httpx.ConnectError('private provider detail', request=request)
    configured(monkeypatch, fail)
    response = review()
    assert response.status_code == 502
    assert 'network' in response.json()['detail'].lower()
    assert 'private provider detail' not in response.text


def test_large_source_returns_validated_preview_hashes_without_sending_full_file(monkeypatch):
    import hashlib
    from backend.app import main
    from backend.app.source_units import MAX_PREVIEW_BYTES
    original = ('#' + 'a' * MAX_PREVIEW_BYTES + '\n' + 'x = 1\n').encode()
    calls = []
    def scan(data):
        return [{'test_id': 'B307', 'line_number': 2, 'description': 'synthetic issue', 'severity': 'HIGH', 'confidence': 'HIGH'}] if data == original else []
    monkeypatch.setattr(main, 'scan_python', scan)
    def handler(request):
        calls.append(json.loads(request.content))
        return reply({'proposed_code':'x = 2\n','explanation':'Change the value.'}) if len(calls) == 1 else reply({'feedback':'Review.','suggested_tests':[]})
    configured(monkeypatch, handler)
    response = client.post('/api/ai-review', headers={'X-AI-Consent':'true'}, files={'file':('input.py',original,'text/plain')}, data={'finding_line':'2','finding_id':'B307'})
    assert response.status_code == 200
    result = response.json()
    assert result['full_original_code'] is None and result['rounds'][0]['full_proposed_code'] is None
    assert result['full_original_sha256'] == hashlib.sha256(original).hexdigest()
    assert result['rounds'][0]['full_proposed_sha256'] == hashlib.sha256(original.replace(b'x = 1',b'x = 2')).hexdigest()
    assert len(json.dumps(calls)) < 20000


@pytest.mark.parametrize('second,status,rank_status', [
    ('x = 3\n', 'changed', 'available'),
    ('x = 1\n', 'unchanged', 'single_candidate'),
    ('x = 2\n', 'duplicate', 'single_candidate'),
])
def test_refinement_distinct_unchanged_and_duplicate(monkeypatch, second, status, rank_status):
    mock_grounded_scan(monkeypatch)
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        data = json.loads(payload['messages'][1]['content'])
        calls.append((payload, data))
        if len(calls) == 1:
            return reply({'proposed_code':'x = 2\n', 'explanation':'first'})
        if len(calls) == 2:
            return reply({'feedback':'Check input.', 'suggested_tests':[]})
        if len(calls) == 3:
            assert data['original_code'] == 'x = 1\n'
            assert data['previous_proposal'] == 'x = 2\n'
            assert data['challenger_feedback'] == 'Check input.'
            assert data['target_finding']['test_id'] == 'B307'
            assert data['verification_summary']['syntax_valid'] is True
            assert 'target_rule_still_reported' in data['verification_summary']
            assert 'distinct alternative to the original and previous proposal' in payload['messages'][0]['content']
            return reply({'proposed_code':second, 'explanation':'second'})
        return reply({'feedback':'Review.', 'suggested_tests':[]})
    configured(monkeypatch, handler)
    response = review(b'x = 1\n', refine=True)
    assert response.status_code == 200
    result = response.json()
    assert len(calls) == 4
    assert result['rounds'][1]['candidate_assessment']['proposal_status'] == status
    assert result['neural_ranking']['status'] == rank_status
    if status != 'changed':
        assert not result['rounds'][1]['candidate_assessment']['ranking_eligible']
    else:
        assert len(result['neural_ranking']['candidates']) == 2
        assert all(isinstance(c['score'], float) for c in result['neural_ranking']['candidates'])

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import ai_agents
from backend.app.main import app

client = TestClient(app)


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


def review(content=b'eval(input())\n', consent=True, name='input.py'):
    headers = {'X-AI-Consent': 'true'} if consent else {}
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
    assert result['manual_review_required'] is True
    assert not marker.exists()
    assert 'test-secret' not in response.text


def test_provider_failure_and_timeout_retries(monkeypatch):
    attempts = []
    def failure(request):
        attempts.append(1)
        return httpx.Response(503, text='sensitive internal error')
    configured(monkeypatch, failure)
    response = review()
    assert response.status_code == 502 and len(attempts) == 2
    assert 'sensitive' not in response.text and 'test-secret' not in response.text
    attempts.clear()
    def timeout(request):
        attempts.append(1)
        raise httpx.ReadTimeout('private detail', request=request)
    # Replace transport factory without wrapping the already monkeypatched class.
    monkeypatch.undo()
    configured(monkeypatch, timeout)
    response = review()
    assert response.status_code == 504 and len(attempts) == 2
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
    assert response.status_code == 502 and len(attempts) == 2


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


def test_network_error_is_distinct(monkeypatch):
    def fail(request):
        raise httpx.ConnectError('private provider detail', request=request)
    configured(monkeypatch, fail)
    response = review()
    assert response.status_code == 502
    assert 'network' in response.json()['detail'].lower()
    assert 'private provider detail' not in response.text

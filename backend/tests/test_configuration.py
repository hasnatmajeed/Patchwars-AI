from pathlib import Path
import logging
import zipfile

import pytest

from backend.app import ai_agents
from scripts import build_submission
from scripts import check_ai_config

NAMES = ('AI_BASE_URL', 'AI_API_KEY', 'AI_MODEL')


def test_default_file_is_project_root():
    assert ai_agents.ENV_PATH == Path(ai_agents.__file__).resolve().parents[2] / '.env'


@pytest.fixture
def local_config(monkeypatch, tmp_path):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / '.env'
    monkeypatch.setattr(ai_agents, 'ENV_PATH', path)
    return path


def test_file_and_current_directory(local_config, monkeypatch, tmp_path):
    local_config.write_text('AI_BASE_URL=https://example.test/v1\nAI_API_KEY=file-key\nAI_MODEL=file-model\n')
    monkeypatch.chdir(tmp_path)
    assert ai_agents.configuration() == ('https://example.test/v1/chat/completions', 'file-key', 'file-model')


def test_environment_precedence_and_empty_fallback(local_config, monkeypatch):
    local_config.write_text('AI_BASE_URL=https://example.test/v1\nAI_API_KEY=file-key\nAI_MODEL=file-model\n')
    monkeypatch.setenv('AI_BASE_URL', 'https://override.test/v1')
    monkeypatch.setenv('AI_API_KEY', '  ')
    monkeypatch.setenv('AI_MODEL', 'override-model')
    assert ai_agents.configuration() == ('https://override.test/v1/chat/completions', 'file-key', 'override-model')


def test_missing_file(local_config, monkeypatch):
    with pytest.raises(ai_agents.AIConfigError, match='AI_BASE_URL'):
        ai_agents.configuration()
    for name, value in zip(NAMES, ('https://example.test/v1', 'env-key', 'env-model')):
        monkeypatch.setenv(name, value)
    assert ai_agents.configuration()[1:] == ('env-key', 'env-model')


def test_diagnostics_do_not_expose_values(local_config, caplog):
    local_config.write_text('AI_BASE_URL=https://user:private-url@example.test\nAI_API_KEY=private-key\nAI_MODEL=private-model\n')
    with caplog.at_level(logging.WARNING), pytest.raises(ai_agents.AIConfigError) as error:
        ai_agents.configuration()
    for secret in ('private-url', 'private-key', 'private-model'):
        assert secret not in str(error.value)
        assert secret not in caplog.text


def test_submission_is_explicit_and_excludes_local_secrets(tmp_path):
    output = tmp_path / 'submission.zip'
    build_submission.build(output)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert names == set(build_submission.FILES)
    assert {'frontend/src/navigation.jsx', 'frontend/src/public-pages.jsx',
            'frontend/src/review-progress.jsx', 'frontend/src/workspace-components.jsx',
            'backend/tests/test_review_stream.py', 'backend/tests/test_zip_review.py',
            'docs/FINAL_PROJECT_REPORT.md', 'docs/ARCHITECTURE.md', 'docs/DEMO_GUIDE.md',
            'docs/TEST_RESULTS.md', 'docs/PROJECT_STATUS.md'} <= names
    assert '.env.example' in names
    assert not any(Path(name).name.lower().startswith(('.env.', 'credentials', 'secret'))
                   for name in names - {'.env.example'})
    assert '.env' not in names
    with pytest.raises(FileExistsError):
        build_submission.build(output)


def test_submission_rejects_secret_even_if_added_to_allowlist(monkeypatch, tmp_path):
    monkeypatch.setattr(build_submission, 'FILES', ('.env.local',))
    with pytest.raises(ValueError, match='Secret paths'):
        build_submission.build(tmp_path / 'submission.zip')


@pytest.mark.parametrize('status', [200, 401])
def test_diagnostic_uses_effective_key_and_hides_response(local_config, monkeypatch, capsys, status):
    import httpx
    local_config.write_text('AI_BASE_URL=https://openrouter.ai/api/v1\nAI_API_KEY=file-private-key\nAI_MODEL=test-model\n')
    monkeypatch.setenv('AI_API_KEY', '  ')
    original = httpx.Client

    def handler(request):
        assert str(request.url) == check_ai_config.KEY_ENDPOINT
        assert request.headers['authorization'] == 'Bearer file-private-key'
        return httpx.Response(status, text='private-provider-response')

    monkeypatch.setattr(check_ai_config.httpx, 'Client',
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert check_ai_config.main() == (0 if status == 200 else 1)
    output = capsys.readouterr().out
    assert f'OpenRouter HTTP status: {status}' in output
    assert 'file-private-key' not in output and 'private-provider-response' not in output
    assert 'AI_API_KEY length: 16' in output


def test_diagnostic_never_sends_other_provider_key(local_config, monkeypatch, capsys):
    local_config.write_text('AI_BASE_URL=https://other.example/v1\nAI_API_KEY=private-key\nAI_MODEL=test-model\n')
    monkeypatch.setattr(check_ai_config.httpx, 'Client', lambda **kwargs: pytest.fail('unexpected request'))
    assert check_ai_config.main() == 1
    assert 'private-key' not in capsys.readouterr().out


def test_diagnostic_redacts_secrets_in_other_fields(local_config, capsys):
    local_config.write_text('AI_BASE_URL=https://private-key@example.test/v1\nAI_API_KEY=private-key\nAI_MODEL=private-key\n')
    assert check_ai_config.main() == 1
    assert 'private-key' not in capsys.readouterr().out

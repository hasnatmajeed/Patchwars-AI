"""Inspect effective AI settings and check an OpenRouter key without exposing it."""
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import ai_agents  # noqa: E402

KEY_ENDPOINT = 'https://openrouter.ai/api/v1/key'


def safe_display(value: str, key: str, *, url: bool = False) -> str:
    if not value:
        return '(not configured)'
    if key and key in value:
        return '(redacted)'
    if url:
        try:
            parsed = urlsplit(value)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or parsed.port is not None):
                return '(invalid or redacted)'
        except ValueError:
            return '(invalid or redacted)'
    if not re.fullmatch(r'[A-Za-z0-9._:/-]+', value):
        return '(invalid or redacted)'
    return value


def main() -> int:
    print(f'Project .env exists: {"yes" if ai_agents.ENV_PATH.is_file() else "no"}')
    try:
        base, key, model = ai_agents.load_ai_settings()
    except ai_agents.AIConfigError:
        print('Configuration could not be read.')
        return 1
    valid = bool(key) and key.isascii() and all(33 <= ord(c) <= 126 for c in key)
    print(f'AI_API_KEY configured: {"yes" if key else "no"}')
    print(f'AI_API_KEY format valid for a Bearer header: {"yes" if valid else "no"}')
    print(f'AI_API_KEY length: {len(key)}')
    print(f'AI_BASE_URL: {safe_display(base, key, url=True)}')
    print(f'AI_MODEL: {safe_display(model, key)}')
    if not valid:
        print('OpenRouter authentication: not tested (key missing or invalid).')
        return 1
    if base.lower() != 'https://openrouter.ai/api/v1' and not key.startswith('sk-or-v1-'):
        print('OpenRouter authentication: not tested (key and base URL do not identify OpenRouter).')
        return 1
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', KEY_ENDPOINT, headers={'Authorization': f'Bearer {key}'}) as response:
                status = response.status_code
    except (httpx.HTTPError, ValueError):
        print('OpenRouter authentication: request failed; no HTTP status received.')
        return 1
    print(f'OpenRouter HTTP status: {status}')
    if status == 200:
        print('OpenRouter authentication: succeeded.')
        return 0
    print('OpenRouter authentication: failed.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

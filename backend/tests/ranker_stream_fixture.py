"""Synthetic, mocked review stream for the frontend integration test."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from backend.app import ai_agents, main

ai_agents.configuration = lambda: ('synthetic', 'synthetic', 'synthetic')
main.scan_python = lambda data, **kwargs: ([{'test_id': 'B307', 'line_number': 1, 'description': 'Synthetic finding', 'severity': 'HIGH', 'confidence': 'HIGH'}] if data == b'x = 1\n' else [])


async def defender(config, source, findings, *args):
    return {'proposed_code': 'x = 3\n' if args else 'x = 2\n', 'explanation': 'Synthetic proposal.'}


async def challenger(config, source, proposed, findings, **kwargs):
    return {'feedback': 'Synthetic review.', 'suggested_tests': ['Check behavior.']}


ai_agents.defender = defender
ai_agents.challenger = challenger
headers = {'X-AI-Consent': 'true'}
if len(sys.argv) > 1 and sys.argv[1] == 'refine':
    headers['X-AI-Refine'] = 'true'
response = TestClient(main.app).post('/api/ai-review/stream', headers=headers,
    files={'file': ('example.py', b'x = 1\n', 'text/plain')})
if response.status_code != 200:
    raise SystemExit('Synthetic review stream failed')
sys.stdout.write(response.text)

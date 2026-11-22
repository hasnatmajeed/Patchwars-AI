import math

from fastapi.testclient import TestClient

from backend.app import ai_agents, main, ranker_demo
from backend.app.patch_ranker import FEATURES, extract_features, load_model, score


def test_demo_runs_real_inference_without_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A hosted provider must not be used by the demo')
    monkeypatch.setattr(ai_agents, 'configuration', forbidden)
    monkeypatch.setattr(ai_agents, 'defender', forbidden)
    monkeypatch.setattr(ai_agents, 'challenger', forbidden)
    captured = []
    real_rank = ranker_demo.rank_candidates
    def checked_rank(original, before, rounds, **kwargs):
        model = load_model()
        for item in rounds:
            features = extract_features(original, item['proposed_code'], before, item['bandit_after'], item['verification'])
            assert len(features) == len(FEATURES) == 11
            captured.append((item['round'], score(model, features)))
        return real_rank(original, before, rounds, **kwargs)
    monkeypatch.setattr(ranker_demo, 'rank_candidates', checked_rank)
    response = TestClient(main.app).get('/api/research/neural-ranking-demo')
    assert response.status_code == 200
    result = response.json()
    assert result['example_id'] == 'eval_numbers' and result['model_version'] == 'synthetic-ranknet-v1'
    candidates = result['candidates']
    assert {item['label'] for item in candidates} == {'A', 'B'}
    assert candidates[0]['code'] != candidates[1]['code']
    by_label = {item['label']: item for item in candidates}
    assert 'B307' in by_label['A']['before_rules'] and 'B307' not in by_label['A']['after_rules']
    assert 'B307' in by_label['B']['after_rules']
    assert all(item['syntax_valid'] and math.isfinite(item['score']) for item in candidates)
    assert [item['score'] for item in candidates] == sorted([item['score'] for item in candidates], reverse=True)
    assert {item['label']: item['score'] for item in candidates} == {'A': captured[0][1], 'B': captured[1][1]}


def test_demo_gracefully_reports_unavailable_model(monkeypatch):
    monkeypatch.setattr(ranker_demo, 'scan_python', lambda data, **kwargs: [])
    monkeypatch.setattr(ranker_demo, 'rank_candidates', lambda *args, **kwargs: {'status': 'unavailable', 'candidates': []})
    response = TestClient(main.app).get('/api/research/neural-ranking-demo')
    assert response.status_code == 503 and 'unavailable' in response.json()['detail'].lower()

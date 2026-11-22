import json
from copy import deepcopy

import pytest

from backend.app.patch_ranker import FEATURES, MODEL_PATH, extract_features, load_model, rank_candidates, score
from backend.app.verification import verify_patch
from ml.train_patch_ranker import split_groups, train


def finding(severity='HIGH', line=1):
    return {'test_id': 'B307', 'line_number': line, 'description': 'example', 'severity': severity}


def candidate(number, code, before, after):
    return {'round': number, 'proposed_code': code, 'bandit_after': after,
            'verification': verify_patch('x = 1\n', code, before, after)}


def test_features_preserve_missing_and_static_differences():
    before = [finding()]
    valid = verify_patch('x = 1\n', 'x = 2\n', before, [])
    missing = verify_patch('x = 1\n', 'x = 2\n', before, None)
    a = extract_features('x = 1\n', 'x = 2\n', before, [], valid)
    b = extract_features('x = 1\n', 'x = 2\n', before, None, missing)
    assert len(a) == len(FEATURES) and a[2] == 0 and b[2] == 1
    assert a[3] == 1 and a[4] == 0 and a[6] == 3
    new = [finding('MEDIUM', 2)]
    v = verify_patch('x = 1\n', 'x = 2\n', before, new)
    assert extract_features('x = 1\n', 'x = 2\n', before, new, v)[5] == 1
    invalid = verify_patch('x = 1\n', 'if:', before, None)
    assert extract_features('x = 1\n', 'if:', before, None, invalid)[0] == 0


def test_training_reproducible_and_nonlinear():
    plus, minus = [1.0] + [0.0] * (len(FEATURES)-1), [0.0] * len(FEATURES)
    first, loss = train([(plus, minus)])
    second, _ = train([(plus, minus)])
    assert first == second and loss > 0 and score(first, plus) > score(first, minus)
    assert len(first['hidden_weights']) > 1


def test_group_split_rejects_family_leakage():
    a = {'id': 'a', 'original': 'a', 'split': 'train', 'family': 'same'}
    b = {'id': 'b', 'original': 'b', 'split': 'validation', 'family': 'same'}
    with pytest.raises(ValueError, match='leakage'):
        split_groups([a, b])
    b['family'] = 'other'
    assert len(split_groups([a, b])[0]) == 1


def test_ranking_missing_model_schema_and_invalid_candidates(tmp_path):
    before = [finding()]
    a = candidate(1, 'x = 2\n', before, [])
    b = candidate(2, 'x = 3\n', before, before)
    invalid = candidate(3, 'if:', before, None)
    assert rank_candidates('x = 1\n', before, [a])['status'] == 'single_candidate'
    assert rank_candidates('x = 1\n', before, [invalid])['status'] == 'no_valid_candidates'
    assert rank_candidates('x = 1\n', before, [a, b], tmp_path / 'missing')['status'] == 'unavailable'
    artifact = deepcopy(load_model()); artifact['features'][0] = 'wrong'
    path = tmp_path / 'model.json'; path.write_text(json.dumps(artifact), encoding='utf-8')
    assert rank_candidates('x = 1\n', before, [a, b], path)['status'] == 'unavailable'
    actual = rank_candidates('x = 1\n', before, [a, b, invalid], MODEL_PATH)
    assert actual['status'] == 'available' and {c['round'] for c in actual['candidates']} == {1, 2}
    assert [c['rank'] for c in actual['candidates']] == [1, 2]


def test_equal_proposals_are_not_ranked_and_inference_failure_is_safe(monkeypatch):
    before = [finding()]
    first = candidate(1, 'x = 2\n', before, [])
    second = candidate(2, 'x = 2\n', before, [])
    ranked = rank_candidates('x = 1\n', before, [first, second])
    assert ranked == {'status': 'single_candidate', 'candidates': [], 'reason': 'identical_candidates'}
    second = candidate(2, 'x = 3\n', before, [])
    def fail(*args):
        raise RuntimeError('private diagnostic')
    monkeypatch.setattr('backend.app.patch_ranker.score', fail)
    result = rank_candidates('x = 1\n', before, [first, second])
    assert result == {'status': 'unavailable', 'candidates': []}


def test_flask_bind_example_uses_actual_scan_and_trained_inference():
    from backend.app.scanner import scan_python
    original = "app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)\n"
    patches = ["app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)\n",
               "import os\nhost = os.environ.get('FLASK_BIND_HOST', '127.0.0.1')\napp.run(host=host, port=5000, debug=False, use_reloader=False)\n"]
    before = scan_python(original.encode())
    target = next(item for item in before if item['test_id'] == 'B104')
    rounds = []
    for index, patch in enumerate(patches, 1):
        after = scan_python(patch.encode())
        verification = verify_patch(original, patch, before, after, target)
        assert verification['syntax_valid'] and verification['target_rule_still_reported'] is False
        assert verification['unrelated_change_possible'] is False and not after
        assert len(extract_features(original, patch, before, after, verification)) == 11
        rounds.append({'round': index, 'proposed_code': patch, 'bandit_after': after, 'verification': verification})
    ranking = rank_candidates(original, before, rounds)
    assert ranking['status'] == 'available'
    assert {item['round'] for item in ranking['candidates']} == {1, 2}
    assert all(isinstance(item['score'], float) for item in ranking['candidates'])

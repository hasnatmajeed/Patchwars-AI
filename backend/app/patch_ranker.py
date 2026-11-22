"""Experimental synthetic-data neural patch ranking; no code is executed."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

MODEL_PATH = Path(__file__).with_name('patch_ranker_model.json')
MODEL_VERSION = 'synthetic-ranknet-v1'
FEATURES = ['syntax_valid', 'syntax_missing', 'scan_missing', 'before_count', 'after_count',
            'introduced_count', 'before_severity', 'after_severity', 'added_lines', 'removed_lines', 'changed_fraction']


def _weighted(findings: list[dict[str, Any]] | None) -> float:
    weights = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
    return float(sum(weights.get(str(f.get('severity', '')).upper(), 0) for f in (findings or [])))


def extract_features(original: str, proposed: str, before: list[dict] | None,
                     after: list[dict] | None, verification: dict[str, Any]) -> list[float]:
    """Use existing static results; missing findings remain explicitly distinct from zero."""
    summary = verification.get('change_summary') or {}
    added = summary.get('lines_added', 0)
    removed = summary.get('lines_removed', 0)
    added = added if isinstance(added, (int, float)) else 0
    removed = removed if isinstance(removed, (int, float)) else 0
    syntax = verification.get('syntax_valid')
    introduced = verification.get('introduced_findings')
    denominator = max(1, len(original.splitlines()) + len(proposed.splitlines()))
    return [float(syntax is True), float(syntax is None), float(before is None or after is None),
            float(len(before or [])), float(len(after or [])), float(len(introduced or [])),
            _weighted(before), _weighted(after), float(added), float(removed), (added + removed) / denominator]


def load_model(path: Path = MODEL_PATH) -> dict[str, Any]:
    if path.stat().st_size > 100_000:
        raise ValueError('Model artifact is too large')
    model = json.loads(path.read_text(encoding='utf-8'))
    if model.get('version') != MODEL_VERSION or model.get('features') != FEATURES:
        raise ValueError('Model version or feature schema mismatch')
    hidden = model['hidden_weights']; biases = model['hidden_bias']; output = model['output_weights']
    if not (isinstance(hidden, list) and 1 <= len(hidden) <= 32 and len(biases) == len(output) == len(hidden)):
        raise ValueError('Invalid model dimensions')
    if any(not isinstance(row, list) or len(row) != len(FEATURES) for row in hidden):
        raise ValueError('Invalid feature dimensions')
    means, scales = model['means'], model['scales']
    if len(means) != len(FEATURES) or len(scales) != len(FEATURES):
        raise ValueError('Invalid normalization dimensions')
    values = [v for row in hidden for v in row] + biases + output + means + scales + [model['output_bias']]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1e6 for v in values) or any(v <= 0 for v in scales):
        raise ValueError('Invalid model values')
    return model


def score(model: dict[str, Any], features: list[float]) -> float:
    x = [(v - m) / s for v, m, s in zip(features, model['means'], model['scales'])]
    hidden = [math.tanh(sum(w * v for w, v in zip(row, x)) + bias)
              for row, bias in zip(model['hidden_weights'], model['hidden_bias'])]
    return sum(w * value for w, value in zip(model['output_weights'], hidden)) + model['output_bias']


def rank_candidates(original: str, before: list[dict] | None, rounds: list[dict],
                    model_path: Path = MODEL_PATH, *, allow_unchanged_demo: bool = False) -> dict[str, Any]:
    """Rank only distinct, grounded, statically checked proposals; never apply one."""
    if not before:
        return {'status': 'no_grounded_findings', 'candidates': []}
    candidates, seen = [], set()
    duplicate = False
    for r in rounds:
        code, v = r.get('proposed_code'), r.get('verification')
        assessment = r.get('candidate_assessment') or {}
        if 'identical_to_round_one' in assessment.get('reasons', []):
            duplicate = True
        if (not isinstance(code, str) or (code == original and not allow_unchanged_demo) or not isinstance(v, dict)
                or assessment.get('ranking_eligible') is False
                or v.get('syntax_valid') is not True or not isinstance(r.get('bandit_after'), list)
                or v.get('target_rule_still_reported') is True or v.get('unrelated_change_possible') is True):
            continue
        if code in seen:
            duplicate = True
            continue
        seen.add(code)
        candidates.append(r)
    if len(candidates) < 2:
        result = {'status': 'single_candidate' if candidates else 'no_valid_candidates', 'candidates': []}
        if duplicate:
            result['reason'] = 'identical_candidates'
        return result
    try:
        model = load_model(model_path)
        ranked = [{'round': r['round'], 'score': score(model, extract_features(original, r['proposed_code'], before,
                    r.get('bandit_after'), r['verification'])),
                   'syntax_valid': True, 'before_count': len(before) if before is not None else None,
                   'after_count': len(r['bandit_after']) if isinstance(r.get('bandit_after'), list) else None}
                  for r in candidates]
        if any(not math.isfinite(item['score']) for item in ranked):
            raise ValueError('Non-finite score')
        ranked.sort(key=lambda item: (-item['score'], item['round']))
        for index, item in enumerate(ranked):
            # Equal scores share a rank; round order only makes presentation stable.
            item['rank'] = ranked[index - 1]['rank'] if index and item['score'] == ranked[index - 1]['score'] else index + 1
        return {'status': 'available', 'model_version': MODEL_VERSION, 'candidates': ranked}
    except Exception:
        # Ranking is advisory: an inference or artifact failure must not discard review results.
        return {'status': 'unavailable', 'candidates': []}

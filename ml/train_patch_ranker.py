"""Train a small tanh RankNet on independently authored synthetic examples."""
from __future__ import annotations

import json
import hashlib
import math
import random
from pathlib import Path

from backend.app.patch_ranker import FEATURES, MODEL_VERSION, extract_features, score
from backend.app.scanner import ScanError, scan_python
from backend.app.verification import verify_patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'ml' / 'patch_ranker_examples.json'
MODEL = ROOT / 'backend' / 'app' / 'patch_ranker_model.json'
REPORT = ROOT / 'ml' / 'results' / 'patch_ranker_metrics.json'
SEED, EPOCHS, HIDDEN, LEARNING_RATE = 42, 500, 8, 0.02


def split_groups(groups: list[dict]) -> tuple[list[dict], list[dict]]:
    train = [g for g in groups if g['split'] == 'train']
    val = [g for g in groups if g['split'] == 'validation']
    if not train or not val or len(train) + len(val) != len(groups):
        raise ValueError('Invalid split')
    ids = [g['id'] for g in groups]
    if (len(ids) != len(set(ids)) or {g['original'] for g in train} & {g['original'] for g in val}
            or {g['family'] for g in train} & {g['family'] for g in val}):
        raise ValueError('Duplicate group or original leakage')
    return train, val


def examples(groups: list[dict]) -> list[tuple[list[float], list[float]]]:
    pairs = []
    for group in groups:
        original = group['original']
        before = scan_python(original.encode())
        preferred = [c for c in group['candidates'] if c['preferred'] is True]
        other = [c for c in group['candidates'] if c['preferred'] is False]
        if not preferred or not other:
            raise ValueError('Each group needs explicitly labeled alternatives')
        vectors = []
        for candidate in group['candidates']:
            code = candidate['code']
            try:
                after = scan_python(code.encode())
            except ScanError:
                after = None
            verification = verify_patch(original, code, before, after)
            vectors.append((candidate['preferred'], extract_features(original, code, before, after, verification)))
        pairs.extend((a, b) for label_a, a in vectors if label_a for label_b, b in vectors if not label_b)
    return pairs


def train(train_pairs: list[tuple[list[float], list[float]]]) -> tuple[dict, float]:
    """Optimize -log(sigmoid(score(preferred)-score(other))) with SGD."""
    rng = random.Random(SEED)
    rows = [row for pair in train_pairs for row in pair]
    means = [sum(row[i] for row in rows) / len(rows) for i in range(len(FEATURES))]
    scales = [max(1.0, math.sqrt(sum((row[i] - means[i]) ** 2 for row in rows) / len(rows))) for i in range(len(FEATURES))]
    model = {'version': MODEL_VERSION, 'features': FEATURES, 'means': means, 'scales': scales,
             'hidden_weights': [[rng.uniform(-0.1, 0.1) for _ in FEATURES] for _ in range(HIDDEN)],
             'hidden_bias': [0.0] * HIDDEN, 'output_weights': [rng.uniform(-0.1, 0.1) for _ in range(HIDDEN)], 'output_bias': 0.0}
    for _ in range(EPOCHS):
        order = list(train_pairs); rng.shuffle(order)
        for positive, negative in order:
            xs = [[(v - m) / s for v, m, s in zip(row, means, scales)] for row in (positive, negative)]
            hs = [[math.tanh(sum(w * v for w, v in zip(weights, x)) + b) for weights, b in zip(model['hidden_weights'], model['hidden_bias'])] for x in xs]
            difference = sum(w * (a - b) for w, a, b in zip(model['output_weights'], hs[0], hs[1]))
            gradient = -1.0 / (1.0 + math.exp(max(-40.0, min(40.0, difference))))
            old_output = model['output_weights'][:]
            for j in range(HIDDEN):
                model['output_weights'][j] -= LEARNING_RATE * gradient * (hs[0][j] - hs[1][j])
                da = gradient * old_output[j] * (1 - hs[0][j] ** 2)
                db = -gradient * old_output[j] * (1 - hs[1][j] ** 2)
                for k in range(len(FEATURES)):
                    model['hidden_weights'][j][k] -= LEARNING_RATE * (da * xs[0][k] + db * xs[1][k])
                model['hidden_bias'][j] -= LEARNING_RATE * (da + db)
    loss = sum(math.log1p(math.exp(-max(-40, min(40, score(model, a) - score(model, b))))) for a, b in train_pairs) / len(train_pairs)
    return model, loss


def evaluate(model: dict, pairs: list[tuple[list[float], list[float]]]) -> dict:
    correct = sum(score(model, a) > score(model, b) for a, b in pairs)
    # Fixed comparator: prefer fewer proposed Bandit findings; ties count as half.
    baseline = sum(1.0 if a[4] < b[4] else 0.5 if a[4] == b[4] else 0.0 for a, b in pairs)
    return {'pairs': len(pairs), 'pairwise_accuracy': correct / len(pairs),
            'top1_accuracy': correct / len(pairs), 'fewer_findings_baseline_accuracy_with_half_ties': baseline / len(pairs)}


def main() -> None:
    data = json.loads(DATA.read_text(encoding='utf-8'))
    train_groups, val_groups = split_groups(data['groups'])
    train_pairs, val_pairs = examples(train_groups), examples(val_groups)
    model, loss = train(train_pairs)
    report = {'model_version': MODEL_VERSION, 'dataset': 'synthetic demonstration only',
              'dataset_sha256': hashlib.sha256(DATA.read_bytes()).hexdigest(),
              'provenance': data['provenance'], 'label_criteria': data['label_criteria'],
              'groups': len(data['groups']), 'candidates': sum(len(g['candidates']) for g in data['groups']),
              'train_groups': [g['id'] for g in train_groups], 'validation_groups': [g['id'] for g in val_groups],
              'train_families': sorted({g['family'] for g in train_groups}),
              'validation_families': sorted({g['family'] for g in val_groups}),
              'group_leakage_detected': False, 'train_pairs': len(train_pairs), 'validation_pairs': len(val_pairs),
              'seed': SEED, 'epochs': EPOCHS, 'hidden_units': HIDDEN, 'learning_rate': LEARNING_RATE,
              'final_training_pairwise_loss': loss, 'training': evaluate(model, train_pairs), 'validation': evaluate(model, val_pairs)}
    MODEL.write_text(json.dumps(model, indent=2) + '\n', encoding='utf-8')
    REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

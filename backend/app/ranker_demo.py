"""Controlled, static-only neural ranking demonstration using project-authored examples."""
import json
from pathlib import Path
from typing import Any

from .patch_ranker import rank_candidates
from .scanner import ScanError, scan_python
from .verification import verify_patch

DATA_PATH = Path(__file__).resolve().parents[2] / 'ml' / 'patch_ranker_examples.json'


class DemoUnavailable(Exception):
    pass


def research_demo() -> dict[str, Any]:
    """Scan and rank two fixed synthetic candidates; never execute source or call a provider."""
    try:
        if DATA_PATH.stat().st_size > 65536:
            raise ValueError('Example data exceeds the demo limit')
        data = json.loads(DATA_PATH.read_text(encoding='utf-8'))
        group = next(item for item in data['groups'] if item['id'] == 'eval_numbers')
        original = group['original']
        examples = group['candidates']
        if (not isinstance(original, str) or len(original.encode('utf-8')) > 6000
                or not isinstance(examples, list) or len(examples) != 2):
            raise ValueError('Invalid demo input')
        codes = [item['code'] for item in examples]
        if any(not isinstance(code, str) or len(code.encode('utf-8')) > 6000 for code in codes) or codes[0] == codes[1]:
            raise ValueError('Invalid demo candidates')
        before = scan_python(original.encode('utf-8'), timeout=10)
        rounds = []
        for index, code in enumerate(codes, 1):
            after = scan_python(code.encode('utf-8'), timeout=10)
            verification = verify_patch(original, code, before, after)
            rounds.append({'round': index, 'proposed_code': code, 'bandit_after': after, 'verification': verification})
        ranking = rank_candidates(original, before, rounds, allow_unchanged_demo=True)
        if ranking['status'] != 'available' or len(ranking['candidates']) != 2:
            raise ValueError('Ranking unavailable')
        candidates = []
        for entry in ranking['candidates']:
            item = rounds[entry['round'] - 1]
            candidates.append({'label': 'A' if entry['round'] == 1 else 'B', 'code': item['proposed_code'],
                               'rank': entry['rank'], 'score': entry['score'],
                               'syntax_valid': item['verification']['syntax_valid'],
                               'before_count': entry['before_count'], 'after_count': entry['after_count'],
                               'introduced_count': len(item['verification']['introduced_findings']),
                               'before_rules': sorted({finding['test_id'] for finding in before}),
                               'after_rules': sorted({finding['test_id'] for finding in item['bandit_after']})})
        return {'model_version': ranking['model_version'], 'example_id': group['id'], 'dataset_split': group['split'],
                'requirement': group['requirement'], 'original_code': original,
                'candidates': candidates}
    except (OSError, ValueError, TypeError, KeyError, StopIteration, UnicodeError, ScanError, json.JSONDecodeError):
        raise DemoUnavailable('The local neural ranking demo is unavailable. Check the model, examples and scanner.') from None

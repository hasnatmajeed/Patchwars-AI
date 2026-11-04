import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ml.train_baseline import SEED, main, read_split, run_experiment


def write_split(path, rows, fields=('source_code', 'raw_label', 'source_hash')):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def record(code, label):
    return {'source_code': code, 'raw_label': label, 'source_hash': 'hash'}


def test_schema_and_raw_label_validation(tmp_path):
    path = tmp_path / 'data.csv'
    write_split(path, [{'source_code': 'abc', 'raw_label': '0'}], ('source_code', 'raw_label'))
    with pytest.raises(ValueError, match='schema'):
        read_split(path, 10)
    for value in ('', '2', ' 1'):
        write_split(path, [record('code', value)])
        with pytest.raises(ValueError, match='raw label'):
            read_split(path, 10)
    write_split(path, [record('abcdefgh', '0'), record('xyz', '1')])
    assert read_split(path, 3, 1) == (['abc'], ['0'])


def test_gate_does_not_read_data_or_create_metrics(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'ml' / 'train_baseline.py'
    result = subprocess.run([sys.executable, str(script), '--data-dir', str(tmp_path / 'missing')], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'raw label meanings are not verified' in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_reject_test_alias_and_output_in_dataset(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    test = data / 'test.csv'
    write_split(test, [record('sample', '0')])
    (data / 'train.csv').hardlink_to(test)
    write_split(data / 'validation.csv', [record('other', '1')])
    with pytest.raises(ValueError, match='Held-out test'):
        run_experiment(data, tmp_path / 'metrics.json', None, 100, 100, None)
    (data / 'train.csv').unlink()
    write_split(data / 'train.csv', [record('other', '0')])
    with pytest.raises(ValueError, match='outside the dataset'):
        run_experiment(data, data / 'metrics.json', None, 100, 100, None)
    assert not (data / 'metrics.json').exists()


def test_deterministic_configuration_and_validation_only(tmp_path):
    pytest.importorskip('sklearn')
    data = tmp_path / 'data'
    data.mkdir()
    write_split(data / 'train.csv', [record('apple safe example', '0'), record('apple repeat example', '0'), record('banana red sample', '1'), record('banana ripe sample', '1')])
    write_split(data / 'validation.csv', [record('apple example', '0'), record('banana sample', '1')])
    # A malformed held-out test file ensures the experiment never reads it.
    (data / 'test.csv').write_text('not,a,valid,dataset', encoding='utf-8')
    first = run_experiment(data, tmp_path / 'one.json', None, 100, 100, None)
    second = run_experiment(data, tmp_path / 'two.json', None, 100, 100, None)
    assert first == second
    assert first['configuration']['seed'] == SEED == 42
    assert first['evaluation_split'] == 'validation'
    assert first['training_examples'] == 4 and first['validation_examples'] == 2
    assert json.loads((tmp_path / 'one.json').read_text(encoding='utf-8')) == first
    assert first['label_semantics'] == 'unverified'
    assert sum(map(sum, first['confusion_matrix'])) == 2
    assert all(0 <= first[name] <= 1 for name in ('accuracy', 'macro_f1', 'balanced_accuracy'))
    assert not list(tmp_path.glob('*.pkl'))


def test_optional_model_persistence_and_row_limit(tmp_path):
    pytest.importorskip('sklearn')
    data = tmp_path / 'data'
    data.mkdir()
    write_split(data / 'train.csv', [record('apple code', '0'), record('banana code', '1'), record('extra code', '0')])
    write_split(data / 'validation.csv', [record('apple', '0'), record('banana', '1')])
    output = tmp_path / 'model.joblib'
    metrics = run_experiment(data, tmp_path / 'metrics.json', output, 100, 100, 2)
    assert metrics['training_examples'] == 2
    assert output.is_file()

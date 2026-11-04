import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ml import train_codebert as codebert


def make_csv(path, rows, fields=('source_code', 'raw_label', 'source_hash')):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_raw_labels_are_not_reinterpreted():
    assert codebert.raw_label('0') == 0
    assert codebert.raw_label('1') == 1
    for bad in ('', '2', ' 1', 'vulnerable'):
        with pytest.raises(ValueError):
            codebert.raw_label(bad)


def test_csv_schema_labels_and_limit(tmp_path):
    path = tmp_path / 'train.csv'
    make_csv(path, [{'source_code': 'code', 'raw_label': '0'}], ('source_code', 'raw_label'))
    with pytest.raises(ValueError, match='schema'):
        codebert.read_split(path)
    make_csv(path, [{'source_code': 'a', 'raw_label': '1', 'source_hash': 'h'}, {'source_code': 'b', 'raw_label': '0', 'source_hash': 'h'}])
    assert codebert.read_split(path, 1) == (['a'], [1])
    make_csv(path, [{'source_code': 'a', 'raw_label': '', 'source_hash': 'h'}])
    with pytest.raises(ValueError, match='Raw label'):
        codebert.read_split(path)


def test_gate_and_configuration(tmp_path):
    assert (codebert.MODEL_ID, codebert.SEED, codebert.TRAIN_LIMIT, codebert.MAX_LENGTH, codebert.BATCH_SIZE, codebert.EPOCHS, codebert.LEARNING_RATE) == ('microsoft/codebert-base', 42, 2000, 256, 8, 1, 2e-5)
    script = Path(codebert.__file__).resolve()
    result = subprocess.run([sys.executable, str(script), '--data-dir', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'raw label semantics are unverified' in result.stderr
    assert not list(tmp_path.iterdir())


def test_held_out_alias_is_rejected(tmp_path):
    train = tmp_path / 'train.csv'
    train.write_text('data', encoding='utf-8')
    (tmp_path / 'validation.csv').hardlink_to(train)
    with pytest.raises(ValueError, match='distinct'):
        codebert.check_paths(tmp_path, tmp_path / 'output')


def test_notebook_structure_and_syntax():
    path = Path(__file__).resolve().parents[1] / 'kaggle' / 'codebert.ipynb'
    notebook = json.loads(path.read_text(encoding='utf-8'))
    assert notebook['nbformat'] == 4
    cells = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']
    assert len(cells) == 4
    for cell in cells:
        compile(''.join(cell['source']), str(path), 'exec')
        assert cell['execution_count'] is None and cell['outputs'] == []
    joined = ''.join(''.join(cell['source']) for cell in cells)
    assert 'train_codebert.py' in joined and '--experimental-raw-labels' in joined

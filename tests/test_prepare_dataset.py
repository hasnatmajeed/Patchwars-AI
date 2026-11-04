import csv
import hashlib
import io
import subprocess
import sys
from pathlib import Path
import zipfile

import pytest

from scripts.prepare_dataset import SCHEMAS, dry_run, prepare, profile


def fixture_zip(path, train, test, bad_schema=False):
    with zipfile.ZipFile(path, 'w') as archive:
        for split, rows in [('train', train), ('test', test)]:
            name, code, label = SCHEMAS[split]
            fields = [code, label, 'patched_function_source', 'repo', 'sha', 'file_path']
            if bad_schema and split == 'test':
                fields.remove(code)
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            for source, value in rows:
                row = {key: '' for key in fields}
                if code in fields:
                    row[code] = source
                row[label] = value
                writer.writerow(row)
            archive.writestr(name, out.getvalue())


def test_profile_exact_duplicates_conflicts_and_overlap(tmp_path):
    archive = tmp_path / 'data.zip'
    fixture_zip(archive, [('same', '0'), ('same', '1'), ('same', '1'), ('', 'x')],
                [('same', '1'), ('unique', '0')])
    result = profile(archive, tmp_path)
    train = result['splits']['train']
    assert train['rows'] == 4
    assert train['labels'] == {'0': 1, '1': 2, 'x': 1}
    assert train['missing_source'] == 1
    assert train['duplicate_code_rows'] == 2
    assert train['conflicting_code_groups'] == 1
    assert result['cross_split_code_groups'] == 1
    assert result['cross_split_rows'] == {'train': 3, 'test': 1}
    assert result['global_conflicting_code_groups'] == 1
    assert profile(archive, tmp_path) == result
    assert sorted(p.name for p in tmp_path.iterdir()) == ['data.zip']


def test_incompatible_schema_rejected(tmp_path):
    archive = tmp_path / 'data.zip'
    fixture_zip(archive, [], [], bad_schema=True)
    with pytest.raises(ValueError, match='Incompatible test schema'):
        profile(archive, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['data.zip']


def test_dry_run_actual_headers_and_no_output(tmp_path):
    archive = tmp_path / 'data.zip'
    headers = {
        'PyCode_Vul- train-set.csv': ['__source_file', 'cve_ids', 'cwe_ids', 'file_path', 'label', 'patched_function_source', 'predicted_cwe_ids', 'repo', 'sha', 'vulnerable_function_source'],
        'PyCode_Vul test-set.csv': ['__source_file', 'cve_ids', 'cwe_ids', 'file_path', 'class', 'patched_function_source', 'predicted_cwe_ids', 'repo', 'sha', 'function_code'],
    }
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name, fields in headers.items():
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            row = {field: '' for field in fields}
            row['label' if 'label' in fields else 'class'] = '1'
            row['vulnerable_function_source' if 'label' in fields else 'function_code'] = 'def f(): pass'
            writer.writerow(row)
            zipped.writestr(name, out.getvalue())
    result = dry_run(archive)
    assert result['splits']['train']['source_column'] == 'vulnerable_function_source'
    assert result['splits']['test']['source_column'] == 'function_code'
    assert result['splits']['train']['label_column'] == 'label'
    assert result['splits']['test']['label_column'] == 'class'
    assert result['splits']['test']['labels'] == {'1': 1}
    assert result['splits']['test']['optional_group_fields'] == ['repo', 'sha', 'file_path']
    assert result['label_semantics'] == 'unverified'
    assert result['preparation_ready'] is False
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'prepare_dataset.py'
    completed = subprocess.run([sys.executable, str(script), str(archive), '--dry-run'], cwd=tmp_path, capture_output=True, text=True)
    assert completed.returncode == 0
    assert 'Preparation blocked' in completed.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ['data.zip']
    blocked = subprocess.run([sys.executable, str(script), str(archive)], cwd=tmp_path, capture_output=True, text=True)
    assert blocked.returncode != 0
    assert 'label semantics' in blocked.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ['data.zip']


def test_dry_run_rejects_missing_fields_and_invalid_labels(tmp_path):
    archive = tmp_path / 'data.zip'
    fixture_zip(archive, [('code', '0')], [('code', '1')], bad_schema=True)
    with pytest.raises(ValueError, match='Incompatible test schema: missing'):
        dry_run(archive)
    fixture_zip(archive, [('code', 'unknown')], [('code', '1')])
    with pytest.raises(ValueError, match='Invalid train label'):
        dry_run(archive)


def test_dry_run_samples_at_most_100_and_preserves_labels(tmp_path):
    archive = tmp_path / 'data.zip'
    fixture_zip(archive, [('code', '0')] * 100 + [('code', 'invalid')], [('code', '1')])
    result = dry_run(archive)
    assert result['splits']['train']['rows_sampled'] == 100
    assert result['splits']['train']['labels'] == {'0': 100}


def read_prepared(output):
    result = {}
    for split in ('train', 'validation', 'test'):
        with (output / f'{split}.csv').open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ['source_code', 'raw_label', 'source_hash']
            result[split] = list(reader)
    return result


def test_prepare_cleaning_conflicts_leakage_and_determinism(tmp_path):
    archive = tmp_path / 'data.zip'
    train = [('keep\r\n  code', '0'), ('keep\r\n  code', '0'), ('', '1'),
             ('invalid', 'x'), ('conflict', '0'), ('cross', '1')]
    train += [(f'code {i}', str(i % 2)) for i in range(80)]
    test = [('cross', '1'), ('test-only', '0'), ('test-only', '0'), ('conflict', '1')]
    fixture_zip(archive, train, test)
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    result = prepare(archive, tmp_path / 'first' / 'processed')
    again = prepare(archive, tmp_path / 'second' / 'processed')
    one = read_prepared(tmp_path / 'first' / 'processed')
    two = read_prepared(tmp_path / 'second' / 'processed')
    assert one == two
    assert result['splits'] == again['splits']
    assert result['original_rows'] == {'train': 86, 'test': 4}
    assert result['conflicting_source_hashes'] == 1
    assert result['skipped']['train'] == {'missing_source': 1, 'invalid_label': 1, 'conflicting_label': 1, 'test_overlap': 1, 'duplicate': 1}
    assert result['skipped']['test'] == {'missing_source': 0, 'invalid_label': 0, 'conflicting_label': 1, 'test_overlap': 0, 'duplicate': 1}
    assert [(r['source_code'], r['raw_label']) for r in one['test']] == [('cross', '1'), ('test-only', '0')]
    assert any(r['source_code'] == 'keep\r\n  code' and r['raw_label'] == '0' for split in ('train', 'validation') for r in one[split])
    hashes = [{row['source_hash'] for row in one[split]} for split in ('train', 'validation', 'test')]
    assert all(not hashes[i] & hashes[j] for i in range(3) for j in range(i))
    assert all(hashlib.sha256(row['source_code'].encode('utf-8')).hexdigest() == row['source_hash'] for rows in one.values() for row in rows)
    assert one['validation'] and one['train']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before


def test_prepare_insufficient_disk_and_existing_output(tmp_path, monkeypatch):
    from collections import namedtuple
    archive = tmp_path / 'data.zip'
    fixture_zip(archive, [('a', '0')], [('b', '1')])
    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr('scripts.prepare_dataset.shutil.disk_usage', lambda _: usage(100, 100, 0))
    output = tmp_path / 'data' / 'processed'
    with pytest.raises(OSError, match='Insufficient disk space'):
        prepare(archive, output)
    assert not output.parent.exists()
    output.mkdir(parents=True)
    (output / 'existing.txt').write_text('preserve')
    with pytest.raises(FileExistsError):
        prepare(archive, output)
    assert (output / 'existing.txt').read_text() == 'preserve'


def test_prepare_schema_failure_and_staging_cleanup(tmp_path, monkeypatch):
    archive = tmp_path / 'data.zip'
    fixture_zip(archive, [('a', '0')], [('b', '1')], bad_schema=True)
    with pytest.raises(ValueError, match='Incompatible test schema'):
        prepare(archive, tmp_path / 'data' / 'processed')
    assert not (tmp_path / 'data').exists()
    fixture_zip(archive, [('a', '0')], [('b', '1')])
    def fail_rename(*args):
        raise OSError('simulated publish failure')
    monkeypatch.setattr('scripts.prepare_dataset.os.rename', fail_rename)
    with pytest.raises(OSError, match='simulated publish failure'):
        prepare(archive, tmp_path / 'data' / 'processed')
    assert list((tmp_path / 'data').iterdir()) == []

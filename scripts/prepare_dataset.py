"""Stream a dataset ZIP into a temporary on-disk index and profile exact code overlap.

Prepare provisional raw-label data or validate a bounded sample. Label semantics
and local provenance remain unverified; no model training is performed.
"""
import argparse
from collections import Counter
from contextlib import closing
import csv
import hashlib
import io
import itertools
import json
import os
import shutil
from pathlib import Path
from contextlib import ExitStack, contextmanager
from typing import Iterator
import sqlite3
import tempfile
import zipfile

SCHEMAS = {
    'train': ('PyCode_Vul- train-set.csv', 'vulnerable_function_source', 'label'),
    'test': ('PyCode_Vul test-set.csv', 'function_code', 'class'),
}
# Optional identifiers are reported when present; they are not verified grouping keys.
GROUP_FIELDS = ('repo', 'sha', 'file_path')
SAMPLE_LIMIT = 100
MAX_ENTRY_BYTES = 256 * 1024 * 1024
MAX_FIELD_BYTES = 2 * 1024 * 1024



def dry_run(archive_path: Path) -> dict:
    """Validate mapped headers and at most 100 rows per split, without writing files."""
    csv.field_size_limit(MAX_FIELD_BYTES)
    result: dict = {'splits': {}, 'label_semantics': 'unverified',
                    'preparation_ready': False}
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        for split, (name, source, label) in SCHEMAS.items():
            if names.count(name) != 1:
                raise ValueError(f'Expected exactly one entry: {name}')
            info = archive.getinfo(name)
            if info.file_size > MAX_ENTRY_BYTES or info.flag_bits & 1:
                raise ValueError(f'Unsupported entry: {name}')
            with archive.open(info) as raw, io.TextIOWrapper(
                    raw, encoding='utf-8-sig', errors='strict', newline='') as stream:
                reader = csv.DictReader(stream, strict=True)
                headers = reader.fieldnames
                if not headers or len(headers) != len(set(headers)):
                    raise ValueError(f'Incompatible {split} schema: missing or duplicate headers')
                missing = {source, label} - set(headers)
                if missing:
                    raise ValueError(f'Incompatible {split} schema: missing {sorted(missing)}')
                stats: dict = {'source_column': source, 'label_column': label,
                               'optional_group_fields': [key for key in GROUP_FIELDS if key in headers],
                               'rows_sampled': 0, 'missing_source': 0, 'labels': Counter()}
                for row in itertools.islice(reader, SAMPLE_LIMIT):
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError(f'Malformed {split} row')
                    value = row[label]
                    if value not in ('0', '1'):
                        raise ValueError(f'Invalid {split} label in sampled row {stats["rows_sampled"] + 1}')
                    stats['rows_sampled'] += 1
                    stats['missing_source'] += not bool(row[source].strip())
                    stats['labels'][value] += 1
                if not stats['rows_sampled']:
                    raise ValueError(f'Empty {split} sample')
                stats['labels'] = dict(stats['labels'])
                result['splits'][split] = stats
    return result



@contextmanager
def source_rows(archive: zipfile.ZipFile, split: str) -> Iterator[csv.DictReader]:
    """Open and validate a split, without extracting it."""
    name, source, label = SCHEMAS[split]
    if archive.namelist().count(name) != 1:
        raise ValueError(f'Expected exactly one entry: {name}')
    info = archive.getinfo(name)
    if info.file_size > MAX_ENTRY_BYTES or info.flag_bits & 1:
        raise ValueError(f'Unsupported entry: {name}')
    with archive.open(info) as raw, io.TextIOWrapper(
            raw, encoding='utf-8-sig', errors='strict', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)) or not {source, label}.issubset(headers):
            raise ValueError(f'Incompatible {split} schema')
        yield reader


def prepare(archive_path: Path, output: Path) -> dict:
    """Stream twice; retain hashes only, hold out test, and publish atomically."""
    csv.field_size_limit(MAX_FIELD_BYTES)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Output already exists: {output}')
    # Check an existing ancestor, before creating any directories or output files.
    ancestor = output.parent
    while not ancestor.exists():
        if ancestor == ancestor.parent:
            raise ValueError('Cannot find output filesystem')
        ancestor = ancestor.parent
    labels_by_hash: dict[str, set[str]] = {}
    test_hashes: set[str] = set()
    original: dict[str, int] = {}
    with zipfile.ZipFile(archive_path) as archive:
        for split in ('train', 'test'):
            _, source, label = SCHEMAS[split]
            count = 0
            with source_rows(archive, split) as rows:
                for row in rows:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError(f'Malformed {split} row')
                    count += 1
                    code, value = row[source], row[label]
                    if not code.strip() or value not in ('0', '1'):
                        continue
                    digest = hashlib.sha256(code.encode('utf-8')).hexdigest()
                    labels_by_hash.setdefault(digest, set()).add(value)
                    if split == 'test':
                        test_hashes.add(digest)
            if not count:
                raise ValueError(f'Empty {split} input')
            original[split] = count
        conflicts = {digest for digest, labels in labels_by_hash.items() if len(labels) > 1}
        # Worst-case CSV quote doubling, hash/CSV overhead per row, and a safety margin.
        required = 2 * sum(archive.getinfo(SCHEMAS[s][0]).file_size for s in SCHEMAS) + 128 * sum(original.values()) + 16 * 1024 * 1024
        free = shutil.disk_usage(ancestor).free
        if free < required:
            raise OSError(f'Insufficient disk space: need {required} bytes, available {free} bytes')
        output.parent.mkdir(parents=True, exist_ok=True)
        result: dict = {'provisional_raw_labels': True, 'original_rows': original,
                        'estimated_required_bytes': required, 'available_bytes': free,
                        'conflicting_source_hashes': len(conflicts),
                        'grouping': 'sha256 source hash; repository grouping unverified',
                        'skipped': {}, 'splits': {}}
        seen: set[str] = set()
        with tempfile.TemporaryDirectory(prefix='.prepare-', dir=output.parent) as temp:
            staging = Path(temp) / 'processed'
            staging.mkdir()
            with ExitStack() as stack:
                writers = {}
                for name in ('train', 'validation', 'test'):
                    stream = stack.enter_context((staging / f'{name}.csv').open('x', encoding='utf-8', newline=''))
                    writer = csv.DictWriter(stream, fieldnames=['source_code', 'raw_label', 'source_hash'], lineterminator='\n')
                    writer.writeheader()
                    writers[name] = writer
                    result['splits'][name] = {'rows': 0, 'raw_labels': {'0': 0, '1': 0}}
                for split in ('test', 'train'):
                    _, source, label = SCHEMAS[split]
                    skipped = dict.fromkeys(('missing_source', 'invalid_label', 'conflicting_label', 'test_overlap', 'duplicate'), 0)
                    result['skipped'][split] = skipped
                    with source_rows(archive, split) as rows:
                        for row in rows:
                            if None in row or any(value is None for value in row.values()):
                                raise ValueError(f'Malformed {split} row')
                            code, value = row[source], row[label]
                            if not code.strip():
                                skipped['missing_source'] += 1
                                continue
                            if value not in ('0', '1'):
                                skipped['invalid_label'] += 1
                                continue
                            digest = hashlib.sha256(code.encode('utf-8')).hexdigest()
                            if digest in conflicts:
                                skipped['conflicting_label'] += 1
                                continue
                            if split == 'train' and digest in test_hashes:
                                skipped['test_overlap'] += 1
                                continue
                            if digest in seen:
                                skipped['duplicate'] += 1
                                continue
                            seen.add(digest)
                            target = 'test' if split == 'test' else ('validation' if int(digest[:16], 16) % 10 == 0 else 'train')
                            writers[target].writerow({'source_code': code, 'raw_label': value, 'source_hash': digest})
                            result['splits'][target]['rows'] += 1
                            result['splits'][target]['raw_labels'][value] += 1
            if output.exists() or output.is_symlink():
                raise FileExistsError(f'Output already exists: {output}')
            os.rename(staging, output)
    return result


def profile(archive_path: Path, workspace: Path) -> dict:
    """Report exact-string statistics, using disk rather than keeping rows in RAM."""
    csv.field_size_limit(MAX_FIELD_BYTES)
    with tempfile.TemporaryDirectory(prefix='.dataset-profile-', dir=workspace) as tmp:
        with closing(sqlite3.connect(str(Path(tmp) / 'profile.sqlite'))) as db, zipfile.ZipFile(archive_path) as archive:
            db.execute('PRAGMA temp_store=FILE')
            db.execute('CREATE TABLE records (split TEXT, code TEXT, label TEXT)')
            result = {'splits': {}}
            names = archive.namelist()
            for split, (name, source, label) in SCHEMAS.items():
                if names.count(name) != 1:
                    raise ValueError(f'Expected exactly one entry: {name}')
                info = archive.getinfo(name)
                if info.file_size > MAX_ENTRY_BYTES or info.flag_bits & 1:
                    raise ValueError(f'Unsupported entry: {name}')
                with archive.open(info) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', errors='strict', newline='') as stream:
                    reader = csv.DictReader(stream, strict=True)
                    headers = reader.fieldnames
                    required = {source, label, 'patched_function_source', 'repo', 'sha', 'file_path'}
                    if not headers or len(headers) != len(set(headers)) or not required.issubset(headers):
                        raise ValueError(f'Incompatible {split} schema')
                    stats = {'columns': headers, 'source_column': source, 'label_column': label,
                             'rows': 0, 'labels': Counter(), 'missing_source': 0,
                             'missing_patched': 0, 'missing_metadata': Counter()}
                    batch = []
                    for row in reader:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError(f'Malformed {split} row')
                        stats['rows'] += 1
                        code = row[source]
                        value = row[label].strip()
                        stats['labels'][value] += 1
                        stats['missing_patched'] += not bool(row['patched_function_source'].strip())
                        for key in ('repo', 'sha', 'file_path'):
                            stats['missing_metadata'][key] += not bool(row[key].strip())
                        if not code.strip():
                            stats['missing_source'] += 1
                            continue
                        batch.append((split, code, value))
                        if len(batch) >= 250:
                            db.executemany('INSERT INTO records VALUES (?, ?, ?)', batch)
                            batch.clear()
                    db.executemany('INSERT INTO records VALUES (?, ?, ?)', batch)
                    stats['labels'] = dict(stats['labels'])
                    stats['missing_metadata'] = dict(stats['missing_metadata'])
                    result['splits'][split] = stats
            db.execute('CREATE INDEX code_index ON records (code, split, label)')
            for split in SCHEMAS:
                count, distinct = db.execute('SELECT count(*), count(DISTINCT code) FROM records WHERE split=?', (split,)).fetchone()
                result['splits'][split]['duplicate_code_rows'] = count - distinct
                result['splits'][split]['conflicting_code_groups'] = db.execute(
                    'SELECT count(*) FROM (SELECT code FROM records WHERE split=? GROUP BY code HAVING count(DISTINCT label)>1)', (split,)).fetchone()[0]
            result['cross_split_code_groups'] = db.execute(
                "SELECT count(*) FROM (SELECT code FROM records GROUP BY code HAVING count(DISTINCT split)>1)").fetchone()[0]
            result['cross_split_rows'] = dict(db.execute(
                "SELECT split, count(*) FROM records WHERE code IN (SELECT code FROM records GROUP BY code HAVING count(DISTINCT split)>1) GROUP BY split"))
            result['global_conflicting_code_groups'] = db.execute(
                'SELECT count(*) FROM (SELECT code FROM records GROUP BY code HAVING count(DISTINCT label)>1)').fetchone()[0]
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path, default=Path('archive.zip'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='validate up to 100 rows per split without writing files')
    mode.add_argument('--prepare', action='store_true', help='generate provisional raw-label CSVs without overwriting')
    mode.add_argument('--profile', action='store_true', help='run the full SQLite-backed profile (may require substantial disk space)')
    args = parser.parse_args()
    if not args.dry_run and not args.profile and not args.prepare:
        parser.exit(1, 'Preparation blocked without an explicit mode: label semantics and local dataset provenance are unverified. Use --dry-run or --prepare for provisional raw-label data.\n')
    try:
        result = dry_run(args.archive) if args.dry_run else (prepare(args.archive, Path.cwd() / 'data' / 'processed') if args.prepare else profile(args.archive, Path.cwd()))
    except (OSError, ValueError, UnicodeError, csv.Error, sqlite3.Error, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Validation failed: {exc}\n')
    print(json.dumps(result, indent=2))
    print('Provisional raw-label data only; label semantics and local dataset provenance remain unverified.' if args.prepare else 'Preparation blocked for verified-label training: semantics and provenance remain unverified; --prepare creates provisional raw-label data.')


if __name__ == '__main__':
    main()

"""Sample CSV entries in a ZIP without extracting or displaying source code."""
import argparse
import collections
import csv
import io
from pathlib import Path
import zipfile

MAX_ENTRY_BYTES = 256 * 1024 * 1024
MAX_FIELD_BYTES = 2 * 1024 * 1024


def audit_entry(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, limit: int) -> set[str]:
    print(f"\n{entry.filename} (uncompressed {entry.file_size:,} bytes)")
    if entry.file_size > MAX_ENTRY_BYTES or entry.flag_bits & 1:
        print("  Skipped: entry exceeds size limit or is encrypted.")
        return set()
    try:
        with archive.open(entry) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            headers = reader.fieldnames
            if not headers or len(headers) != len(set(headers)):
                print("  Skipped: missing or duplicate column headers.")
                return set()
            print("  Columns: " + ", ".join(headers))
            code = [h for h in headers if ('source' in h.lower() or 'code' in h.lower()) and h.lower() != '__source_file']
            labels = [h for h in headers if h.lower() in ('label', 'class', 'target') or 'cwe' in h.lower() or 'cve' in h.lower()]
            relevant = list(dict.fromkeys(code + labels))
            missing = collections.Counter()
            distributions = {h: collections.Counter() for h in labels}
            python_like = collections.Counter()
            seen = set()
            duplicates = malformed = replacements = count = 0
            while count < limit:
                try:
                    row = next(reader)
                except StopIteration:
                    break
                count += 1
                if None in row or any(v is None for v in row.values()):
                    malformed += 1
                values = tuple(row.get(h) or '' for h in headers)
                if values in seen:
                    duplicates += 1
                else:
                    seen.add(values)
                replacements += sum(v.count('\ufffd') for v in values)
                for h in relevant:
                    value = (row.get(h) or '').strip()
                    if not value:
                        missing[h] += 1
                    if h in distributions and value:
                        # Only categorical-looking values are shown, never arbitrary long content.
                        if len(value) <= 80 and '\n' not in value and '\r' not in value:
                            distributions[h][value] += 1
                        else:
                            distributions[h]['<long or multiline value>'] += 1
                    if h in code and ('def ' in value or 'import ' in value or 'class ' in value):
                        python_like[h] += 1
            print(f"  Sample: {count} data rows (first rows, not full dataset); malformed widths: {malformed}; decoding replacements: {replacements}")
            print(f"  Exact duplicate full rows in sample: {duplicates}")
            print('  Candidate code columns: ' + (', '.join(code) or 'none'))
            print('  Candidate labels: ' + (', '.join(labels) or 'none'))
            for h in relevant:
                extra = f'; Python-like markers: {python_like[h]}' if h in code else ''
                print(f"  {h}: missing {missing[h]}{extra}")
                if h in distributions:
                    top = distributions[h].most_common(10)
                    print(f"    Sample values (top 10): {top}; distinct nonempty values: {len(distributions[h])}")
            return set(headers)
    except (OSError, RuntimeError, UnicodeError, csv.Error, zipfile.BadZipFile) as exc:
        print(f"  Could not complete sample: {type(exc).__name__}: {exc}")
        return set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, nargs='?', default=Path('archive.zip'))
    parser.add_argument('--rows', type=int, default=2000, help='maximum rows per CSV (1–2000)')
    args = parser.parse_args()
    if not 1 <= args.rows <= 2000:
        parser.error('--rows must be between 1 and 2000')
    csv.field_size_limit(MAX_FIELD_BYTES)
    try:
        with zipfile.ZipFile(args.archive) as archive:
            entries = archive.infolist()
            print(f"Archive: {args.archive} ({args.archive.stat().st_size:,} bytes); {len(entries)} entries")
            schemas = {}
            for entry in entries:
                if entry.is_dir() or not entry.filename.lower().endswith('.csv'):
                    print(f"  Non-CSV entry skipped: {entry.filename!r}")
                    continue
                schemas[entry.filename] = audit_entry(archive, entry, args.rows)
            for name, columns in schemas.items():
                if columns:
                    for other, other_columns in schemas.items():
                        if other != name and other_columns:
                            print(f"Only in {name} versus {other}: {', '.join(sorted(columns - other_columns)) or '(none)'}")
    except (OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Cannot read archive: {exc}\n")


if __name__ == '__main__':
    main()


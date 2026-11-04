"""Exploratory raw-label baseline; no vulnerability meaning is inferred."""
import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Sequence

SEED = 42
MAX_CSV_FIELD = 2 * 1024 * 1024


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def read_split(path: Path, max_chars: int, limit: int | None = None) -> tuple[list[str], list[str]]:
    """Read one prepared split; truncate code only in memory for this experiment."""
    csv.field_size_limit(MAX_CSV_FIELD)
    texts: list[str] = []
    labels: list[str] = []
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)) or not {'source_code', 'raw_label', 'source_hash'}.issubset(headers):
            raise ValueError(f'Invalid CSV schema: {path}')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed CSV row: {path}')
            if row['raw_label'] not in ('0', '1'):
                raise ValueError(f'Missing or invalid raw label in {path} at row {reader.line_num}')
            if not row['source_code'].strip():
                raise ValueError(f'Missing source in {path} at row {reader.line_num}')
            texts.append(row['source_code'][:max_chars])
            labels.append(row['raw_label'])
            if limit is not None and len(texts) >= limit:
                break
    if not texts:
        raise ValueError(f'Empty dataset: {path}')
    return texts, labels


def run_experiment(data_dir: Path, metrics_path: Path, model_path: Path | None,
                   max_features: int, max_chars: int, train_limit: int | None) -> dict:
    """Fit on train and report on validation only; paths for test are never accepted."""
    train_path = data_dir / 'train.csv'
    validation_path = data_dir / 'validation.csv'
    # Prevent symlink/hardlink aliases for the standard held-out test split.
    test_path = data_dir / 'test.csv'
    if train_path.resolve() == validation_path.resolve() or (train_path.exists() and validation_path.exists() and train_path.samefile(validation_path)):
        raise ValueError('Training and validation must be different files')
    if test_path.exists():
        for path in (train_path, validation_path):
            if path.resolve() == test_path.resolve() or (path.exists() and path.samefile(test_path)):
                raise ValueError('Held-out test data cannot be used in experiments')
    outputs = [metrics_path] + ([model_path] if model_path is not None else [])
    if len({p.resolve() for p in outputs}) != len(outputs):
        raise ValueError('Metrics and model paths must differ')
    for output in outputs:
        if output.exists() or output.is_symlink():
            raise FileExistsError(f'Output already exists: {output}')
        if output.resolve().is_relative_to(data_dir.resolve()):
            raise ValueError('Outputs must be outside the dataset directory')

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
    from sklearn.pipeline import make_pipeline

    train_text, train_labels = read_split(train_path, max_chars, train_limit)
    validation_text, validation_labels = read_split(validation_path, max_chars)
    if set(train_labels) != {'0', '1'}:
        raise ValueError('Training data must contain both raw labels')
    model = make_pipeline(
        TfidfVectorizer(analyzer='char', ngram_range=(3, 5), max_features=max_features, dtype='float32'),
        LogisticRegression(random_state=SEED, max_iter=1000),
    )
    model.fit(train_text, train_labels)
    predicted = model.predict(validation_text)
    result = {
        'experiment': 'exploratory_raw_labels', 'label_semantics': 'unverified',
        'evaluation_split': 'validation', 'labels': ['0', '1'],
        'training_examples': len(train_labels), 'validation_examples': len(validation_labels),
        'accuracy': float(accuracy_score(validation_labels, predicted)),
        'macro_f1': float(f1_score(validation_labels, predicted, labels=['0', '1'], average='macro', zero_division=0)),
        'balanced_accuracy': float(balanced_accuracy_score(validation_labels, predicted)),
        'confusion_matrix': confusion_matrix(validation_labels, predicted, labels=['0', '1']).tolist(),
        'configuration': {'seed': SEED, 'max_features': max_features, 'max_chars': max_chars,
                          'train_limit': train_limit, 'ngram_range': [3, 5]},
    }
    if model_path is not None:
        import joblib
        with model_path.open('xb') as stream:
            joblib.dump(model, stream)
    with metrics_path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experimental-raw-labels', action='store_true', help='explicitly allow an exploratory raw-label experiment')
    parser.add_argument('--data-dir', type=Path, default=Path('data/processed'))
    parser.add_argument('--metrics-output', type=Path, default=Path('baseline_metrics.json'))
    parser.add_argument('--model-output', type=Path, help='optional explicit path for model persistence')
    parser.add_argument('--max-features', type=positive_int, default=15000)
    parser.add_argument('--max-chars', type=positive_int, default=10000)
    parser.add_argument('--train-limit', type=positive_int)
    args = parser.parse_args(argv)
    if not args.experimental_raw_labels:
        print('Training blocked: raw label meanings are not verified. For exploratory raw-label work only, explicitly pass --experimental-raw-labels.', file=sys.stderr)
        return 2
    try:
        metrics = run_experiment(args.data_dir, args.metrics_output, args.model_output,
                                 args.max_features, args.max_chars, args.train_limit)
    except ImportError as exc:
        print(f'ML dependency unavailable: {exc}. Install ml/requirements.txt in the Kaggle environment.', file=sys.stderr)
        return 1
    except (OSError, ValueError, csv.Error) as exc:
        print(f'Experiment failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

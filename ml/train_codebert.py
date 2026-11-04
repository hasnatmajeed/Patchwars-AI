"""Kaggle GPU-only CodeBERT experiment using unverified raw labels."""
import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Sequence

MODEL_ID = 'microsoft/codebert-base'
SEED = 42
TRAIN_LIMIT = 2000
MAX_LENGTH = 256
MAX_CHARS = 10000
BATCH_SIZE = 8
EPOCHS = 1
LEARNING_RATE = 2e-5


def raw_label(value: str) -> int:
    if value not in ('0', '1'):
        raise ValueError('Raw label must be exactly 0 or 1')
    return int(value)


def read_split(path: Path, limit: int | None = None) -> tuple[list[str], list[int]]:
    csv.field_size_limit(2 * 1024 * 1024)
    texts: list[str] = []
    labels: list[int] = []
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(set(headers)) or not {'source_code', 'raw_label', 'source_hash'}.issubset(headers):
            raise ValueError(f'Invalid CSV schema: {path.name}')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed CSV row in {path.name}')
            if not row['source_code'].strip():
                raise ValueError(f'Missing source in {path.name}')
            texts.append(row['source_code'][:MAX_CHARS])
            labels.append(raw_label(row['raw_label']))
            if limit is not None and len(texts) >= limit:
                break
    if not texts:
        raise ValueError(f'Empty dataset: {path.name}')
    return texts, labels


def check_paths(data_dir: Path, output: Path) -> tuple[Path, Path]:
    train, validation, test = (data_dir / name for name in ('train.csv', 'validation.csv', 'test.csv'))
    if not train.is_file() or not validation.is_file():
        raise ValueError('train.csv and validation.csv are required')
    if train.samefile(validation) or (test.exists() and (train.samefile(test) or validation.samefile(test))):
        raise ValueError('Train and validation must be distinct from each other and the held-out test')
    working = Path('/kaggle/working').resolve()
    if not working.is_dir() or not output.resolve().is_relative_to(working) or output.resolve() == working:
        raise ValueError('Output must be a new directory under /kaggle/working')
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Output already exists: {output}')
    return train, validation


def train(data_dir: Path, output: Path) -> dict:
    import torch
    import transformers
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    train_path, validation_path = check_paths(data_dir, output)
    if not torch.cuda.is_available():
        raise RuntimeError('A Kaggle GPU with CUDA is required; CPU training is disabled')
    train_text, train_labels = read_split(train_path, TRAIN_LIMIT)
    val_text, val_labels = read_split(validation_path)
    if len(train_text) != TRAIN_LIMIT or set(train_labels) != {0, 1}:
        raise ValueError('Initial experiment requires 2000 training rows containing both raw labels')
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_ID, num_labels=2, id2label={0: 'RAW_0', 1: 'RAW_1'},
        label2id={'RAW_0': 0, 'RAW_1': 1})
    model.to('cuda')
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    order = list(range(len(train_text)))
    random.shuffle(order)
    model.train()
    for start in range(0, len(order), BATCH_SIZE):
        indices = order[start:start + BATCH_SIZE]
        batch = tokenizer([train_text[i] for i in indices], padding=True, truncation=True,
                          max_length=MAX_LENGTH, return_tensors='pt')
        batch = {key: value.to('cuda') for key, value in batch.items()}
        labels = torch.tensor([train_labels[i] for i in indices], device='cuda')
        optimizer.zero_grad(set_to_none=True)
        loss = model(**batch, labels=labels).loss
        loss.backward()
        optimizer.step()
    model.eval()
    predicted: list[int] = []
    with torch.no_grad():
        for start in range(0, len(val_text), BATCH_SIZE):
            batch = tokenizer(val_text[start:start + BATCH_SIZE], padding=True, truncation=True,
                              max_length=MAX_LENGTH, return_tensors='pt')
            logits = model(**{key: value.to('cuda') for key, value in batch.items()}).logits
            predicted.extend(logits.argmax(dim=-1).cpu().tolist())
    config = {'model': MODEL_ID, 'seed': SEED, 'training_limit': TRAIN_LIMIT,
              'max_sequence_length': MAX_LENGTH, 'max_source_chars': MAX_CHARS,
              'batch_size': BATCH_SIZE, 'epochs': EPOCHS, 'learning_rate': LEARNING_RATE,
              'torch_version': torch.__version__, 'transformers_version': transformers.__version__}
    metrics = {'experiment': 'exploratory_raw_labels', 'label_semantics': 'unverified',
               'evaluation_split': 'validation', 'labels': ['0', '1'],
               'training_examples': len(train_labels), 'validation_examples': len(val_labels),
               'accuracy': float(accuracy_score(val_labels, predicted)),
               'macro_f1': float(f1_score(val_labels, predicted, labels=[0, 1], average='macro', zero_division=0)),
               'balanced_accuracy': float(balanced_accuracy_score(val_labels, predicted)),
               'confusion_matrix': confusion_matrix(val_labels, predicted, labels=[0, 1]).tolist(),
               'configuration': config}
    output.mkdir(parents=False, exist_ok=False)
    model.save_pretrained(output / 'model', safe_serialization=True)
    tokenizer.save_pretrained(output / 'model')
    (output / 'training_config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return metrics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experimental-raw-labels', action='store_true')
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('/kaggle/working/codebert-experiment'))
    args = parser.parse_args(argv)
    if not args.experimental_raw_labels:
        print('Training blocked: raw label semantics are unverified; use --experimental-raw-labels only for exploratory research.', file=sys.stderr)
        return 2
    try:
        result = train(args.data_dir, args.output_dir)
    except (ImportError, OSError, ValueError, RuntimeError, csv.Error) as exc:
        print(f'Experiment failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

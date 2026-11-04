# CodeBERT exploratory training on Kaggle

This prepares a raw-label classifier using `microsoft/codebert-base` and a two-class classification head. Label `0` is stored as class index 0 and label `1` as class index 1; neither is assigned a vulnerability meaning. This is not a patch-reliability ranking model. Repository and near-duplicate leakage remain unresolved, so compare validation numbers cautiously and do not make security claims from them. Review the dataset license, underlying repository rights and permission to upload source code before using Kaggle.

## Files to upload

Use these existing local files:

- `E:\PatchWars Ai\data\processed\train.csv`
- `E:\PatchWars Ai\data\processed\validation.csv`
- `E:\PatchWars Ai\ml\train_codebert.py`
- `E:\PatchWars Ai\kaggle\codebert.ipynb` (import into the notebook; do not add it to the dataset)

Keep `test.csv` and `archive.zip` out of this experiment. The script reads only files named `train.csv` and `validation.csv`; do not rename a copy of the held-out test as either file. The local archive and prepared CSVs are not modified.

## Update the private dataset and create the notebook

1. Open your existing private dataset on Kaggle. Use **New Version** / **Update**, add `train_codebert.py` next to `train.csv` and `validation.csv`, and save a new private version. Keep the earlier script if you still need the baseline; the three CodeBERT files must be in the same folder. If the existing private dataset contains `test.csv`, create a separate private dataset with only the three CodeBERT files instead.
2. Open a Kaggle notebook, import your local `kaggle/codebert.ipynb` using **File > Import Notebook**, and attach the new dataset version using **Add Input**. Keep the notebook private. Kaggle interface names may change.
3. In notebook settings, choose a GPU accelerator. Enable internet for package installation and the Hugging Face pretrained weights download. The notebook checks `nvidia-smi`, CUDA in PyTorch, and dependency versions. It installs missing packages only inside Kaggle. If CUDA-compatible PyTorch is unavailable, it stops; it never falls back to CPU training.
4. Run cells in order. The script downloads `microsoft/codebert-base` weights on Kaggle and trains a new classification head and encoder. The first run uses the first 2,000 training rows in file order, the full validation split, seed 42, 256 tokens, batch size 8, one epoch, and AdamW learning rate 2e-5. Source is truncated to 10,000 characters before tokenization. It uses sparse batches rather than loading model inputs for all rows onto the GPU; loaded CPU source text and weights still require memory.
5. After completion, inspect `/kaggle/working/codebert-experiment/metrics.json` and `training_config.json`. The `model/` directory contains the checkpoint and tokenizer. Save a notebook version and use its Output tab to download the files; for multiple files, use Kaggle's output download controls. Preserve the files securely and share only `metrics.json` for review.
6. The output directory must not already exist. Before a rerun, download or move previous output or start with a clean working directory; an interrupted save can leave a partial directory that must be handled manually.

The script will only write under `/kaggle/working`, requires `--experimental-raw-labels`, checks for a CUDA GPU, and refuses to overwrite the output directory. The notebook runs:

```bash
python /kaggle/input/YOUR_DATASET/train_codebert.py --experimental-raw-labels \
  --data-dir /kaggle/input/YOUR_DATASET \
  --output-dir /kaggle/working/codebert-experiment
```

The script uses a fixed seed; exact reproducibility across GPU types, CUDA and dependency versions is not guaranteed. It records PyTorch and Transformers versions; Hugging Face model revisions are not pinned. The training path and download have not yet been verified on Kaggle.

## Compare with the baseline

The downloaded baseline metrics in `ml/results/metrics.json` report 2,000 training and 1,486 validation rows: accuracy 0.84926, macro F1 0.84124, balanced accuracy 0.83516, and confusion matrix `[[798, 71], [153, 464]]` (rows actual raw 0/1, columns predicted raw 0/1). Compare those with the same fields in CodeBERT's metrics. Both use the first 2,000 training rows and full validation data, but model tokenization and preprocessing differ. Repeatedly choosing models using validation can overfit it; the original test remains held out for a separately authorized final evaluation after label semantics, provenance, rights and leakage checks are resolved.

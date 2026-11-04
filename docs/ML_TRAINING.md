# Exploratory ML baseline

The character n-gram TF-IDF and logistic regression baseline offers a modest reference for later comparisons. It learns patterns associated with raw dataset values, not verified vulnerability states. An exploratory CodeBERT GPU pipeline is prepared in [CODEBERT_TRAINING.md](CODEBERT_TRAINING.md); vulnerability claims remain blocked by the label contract, data rights, leakage risks and evaluation protocol.

The prepared splits contain 12,702 training, 1,486 validation and 3,563 held-out test records. The original inputs contained 14,248 train and 3,563 test records. Exact source-hash intersections were zero during preparation, but repository and near-duplicate leakage remain unresolved. The aggregate class totals corroborate a possible 0/1 interpretation; they do not establish the meaning of either label in both splits. Do not make security or vulnerability-detection claims from these exploratory metrics.

The script defaults to a refusal before reading data or importing scikit-learn. `--experimental-raw-labels` explicitly permits an exploratory experiment; this is not approval for security claims or production integration. The script reads only `train.csv` and `validation.csv` from the selected data directory, fits on train, and reports accuracy, macro F1, balanced accuracy and a confusion matrix on validation. It never intentionally opens `test.csv`; it rejects ordinary test-file symlink or hardlink aliases. The caller must provide genuine prepared split files: renamed copies of test data cannot be automatically identified. Keep the held-out test split out of tuning and routine experiments.

In Kaggle, first verify permission to upload and use the source data and review attribution and underlying repository rights. Upload only the prepared train and validation CSVs as a private Kaggle dataset if permitted; keep the held-out test elsewhere. Make the script and `ml/requirements.txt` available to the notebook. Use a compatible Python environment with scikit-learn installed from that file if it is not already present. Record the actual Python and scikit-learn versions and the dataset identity alongside experiment results. Example command in a notebook, with paths adjusted to the private dataset:

```bash
python ml/train_baseline.py --experimental-raw-labels \
  --data-dir /kaggle/input/YOUR_DATASET \
  --train-limit 1000 --max-features 15000 --max-chars 10000 \
  --metrics-output /kaggle/working/baseline_metrics.json
```

The first `train-limit` rows are used in file order, so a small run is not necessarily representative and must include both raw labels. Omit the limit only when resources allow. Character 3-5 grams remain sparse; vocabulary size and per-source character count are bounded, but the selected source text, validation text and sparse matrices still consume memory. Repeated experiments use seed 42; reproducibility across dependency versions and platforms is not guaranteed. The metrics JSON records configuration, raw-label status, split name and counts. Existing outputs are not overwritten. A model is saved only with an explicit `--model-output` path; serialized models must only be loaded from trusted sources.

Before meaningful vulnerability classification or security claims, obtain an authoritative split-specific label definition, independently confirm dataset provenance and applicable license and third-party code rights, review label quality and potential project/near-duplicate leakage, and establish an appropriate held-out evaluation protocol. The dataset card's CC BY 4.0 declaration and count-based label inference are documented with their limitations in `DATASET_PREPARATION.md`.

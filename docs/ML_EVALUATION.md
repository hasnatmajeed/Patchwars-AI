# Exploratory ML evaluation

Both experiments classify the dataset's **unverified raw labels 0 and 1**. These validation results are exploratory and neither model is validated for production security claims. The local metric files are [baseline](../ml/results/metrics.json) and [CodeBERT](../ml/results/codebert_metrics.json).

## Experimental setup

The TF-IDF character 3–5-gram and logistic regression baseline ran on Kaggle CPU. CodeBERT (`microsoft/codebert-base` with a two-class classification head) ran on a Kaggle T4 GPU for one epoch. Both used the first 2,000 training rows in file order, seed 42, and the 1,486-row validation split. The baseline used up to 5,000 features; CodeBERT used 256 tokens, batch size 8 and learning rate 2e-5. Both limited source text to 10,000 characters, but their representations and preprocessing differ. The ordered training subset may not be representative. These are single runs, so variability is unknown.

Kaggle reported saving the CodeBERT model, tokenizer and metrics. The metrics are present locally; no local CodeBERT checkpoint or tokenizer was found under `ml`. Their availability elsewhere locally has not been verified. The baseline notebook documentation says it did not save a model.

## Validation comparison

Differences are CodeBERT minus baseline, in percentage points. Higher is better for all three metrics.

| Metric | TF-IDF + logistic regression | CodeBERT | Difference |
| --- | ---: | ---: | ---: |
| Accuracy | 84.93% | 82.37% | -2.56 pp |
| Macro F1 | 84.12% | 80.54% | -3.59 pp |
| Balanced accuracy | 83.52% | 79.45% | -4.07 pp |

The baseline performed better on all three measures in this comparison. The confusion matrices below have actual raw classes as rows and predicted raw classes as columns:

| Model | Actual 0 → predicted 0 | Actual 0 → predicted 1 | Actual 1 → predicted 0 | Actual 1 → predicted 1 |
| --- | ---: | ---: | ---: | ---: |
| TF-IDF + logistic regression | 798 | 71 | 153 | 464 |
| CodeBERT | 840 | 29 | 233 | 384 |

CodeBERT correctly classified 42 more class-0 examples, but misclassified 80 more class-1 examples as class 0. The validation set contains 869 class-0 and 617 class-1 examples. Since label meanings are unverified, these counts cannot be assigned verified vulnerability or security interpretations.

## Findings and limitations

One epoch and 2,000 ordered examples may be insufficient to adapt CodeBERT's pretrained representations and new classification head; hyperparameters, truncation to 256 tokens, and training variability may also affect results. Character n-grams can be strong on recurring lexical patterns in a small dataset. These are plausible explanations, not established causes; no ablation or repeated-run evidence identifies the cause here.

The experiment is an exploratory neural classifier of raw labels intended for vulnerability classification research. Neural patch-reliability ranking is a different task: it ranks candidate patches by their expected reliability and requires suitable patch-and-outcome labels. These classification results do not demonstrate such a ranker or patch correctness.

The split-specific label contract, label quality, dataset provenance, applicable dataset and underlying-code rights, and repository and near-duplicate leakage remain unresolved. Exact source-hash intersections were zero in preparation, which does not rule out those leakage risks. The held-out test split was not used for these reported results; validation model selection may itself overfit validation. Independent rights and provenance checks, verified labels and leakage-aware evaluation are needed before meaningful security claims or a final held-out evaluation. See [dataset preparation](DATASET_PREPARATION.md) for the evidence and qualifications.

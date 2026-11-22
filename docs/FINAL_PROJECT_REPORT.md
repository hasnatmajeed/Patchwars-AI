# Final project report

PATCHWARS AI is a final-year prototype for inspecting Python source with static analysis and exploring AI-assisted patch review. Its goal is to present findings, an optional proposed fix and independent critique for human evaluation. It does not establish that code is secure or behaviorally correct.

## Implemented modules

The React/Vite website provides information pages, upload, scan results, one-file AI review, streaming progress, review results and read-only code comparison. FastAPI validates uploads, runs Bandit, coordinates Defender and Challenger, and compares static findings. ZIP projects can be scanned and one validated Python member selected for a review. Hosted review requires explicit consent; optional refinement permits one additional round. Partial results preserve an available proposal when a later stage fails.

Notebook code cells are scanned separately when valid standalone Python; magic, shell and unsupported or invalid cells are reported as skipped. Larger source files can be reviewed only through a server-validated finding and bounded enclosing region. Scoped verification and proposals do not establish whole-file or whole-notebook correctness.

The API exposes `GET /health`, `POST /api/inspect`, `POST /api/scan`, `POST /api/ai-review`, and `POST /api/ai-review/stream`. The streaming endpoint emits fixed milestones and a final result or safe error. See [architecture](ARCHITECTURE.md) and [README](../README.md) for contracts and limits.

## Research track

Dataset preparation maps split-specific source and raw-label columns, filters invalid and exact duplicate/conflicting examples, and records hashes and overlap. Label semantics, provenance, rights, repository grouping and near-duplicate leakage remain unresolved. The held-out test split was not used in the reported evaluations.

The saved validation artifacts report the following single exploratory runs, not results reproduced during final packaging:

| Model | Accuracy | Macro F1 | Balanced accuracy |
| --- | ---: | ---: | ---: |
| Character TF-IDF + logistic regression | 84.93% | 84.12% | 83.52% |
| CodeBERT classification head | 82.37% | 80.54% | 79.45% |

Both used the first 2,000 training rows and 1,486 validation rows with unverified raw labels. The baseline used character 3–5 grams; CodeBERT ran one epoch with 256-token inputs. See [ML evaluation](ML_EVALUATION.md) and the saved JSON metrics for configuration and limitations. Neither experiment proves patch reliability; CodeBERT is not integrated into the scanner.

## Security and limitations

Uploads are bounded; ZIP metadata is checked for unsafe paths, duplicates, encryption, symlinks and unsupported compression. Python source is statically scanned via temporary files and is not executed. ZIP paths are not extracted to disk. Only the selected source and relevant context are sent to the hosted provider after consent. Generated patches are not applied and suggested tests are not run. Local `.env` configuration is excluded from source control and the submission allowlist. Static findings, prompt isolation and automated checks are not security guarantees.

The prototype has no implemented sandboxed functional execution or validated real-world patch-reliability ranker. A separate experimental neural model compares existing candidates using synthetic demonstration labels; its two-group validation is not evidence of reliability. Independent dataset rights, provenance, label verification, leakage analysis, held-out evaluation, browser accessibility rehearsal and a live-provider demo remain work for the project owner. See [project status](PROJECT_STATUS.md) and [test results](TEST_RESULTS.md).

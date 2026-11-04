# Dataset audit

`archive.zip` is 14,636,510 bytes and contains two CSV entries. No files were extracted or executed.

| Entry | Uncompressed bytes | Compressed bytes |
| --- | ---: | ---: |
| `PyCode_Vul test-set.csv` | 19,843,261 | 3,208,963 |
| `PyCode_Vul- train-set.csv` | 72,631,752 | 11,427,197 |

Train columns: `__source_file`, `cve_ids`, `cwe_ids`, `file_path`, `label`, `patched_function_source`, `predicted_cwe_ids`, `repo`, `sha`, `vulnerable_function_source`.

Test columns: `__source_file`, `cve_ids`, `cwe_ids`, `file_path`, `class`, `patched_function_source`, `predicted_cwe_ids`, `repo`, `sha`, `function_code`.

## Sample findings

The script inspected the first 2,000 data rows of each CSV, not a random or full sample. Counts below are sample counts, not dataset totals. Python-like means a simple text marker was found, not that code was parsed or verified.

| Finding | Train | Test |
| --- | ---: | ---: |
| Binary label 0 | 1,096 | 1,128 |
| Binary label 1 | 904 | 872 |
| Missing binary label | 0 | 0 |
| Missing primary code (`vulnerable_function_source` / `function_code`) | 9 | 0 |
| Python-like markers in primary code | 1,991 | 2,000 |
| Missing `patched_function_source` | 14 | 10 |
| Python-like markers in patched code | 1,986 | 1,990 |
| Missing `predicted_cwe_ids` | 728 | 781 |
| Exact duplicate complete rows | 0 | 0 |
| Malformed row widths / decoding replacements | 0 / 0 | 0 / 0 |

`cwe_ids` was `UNKNOWN` in all 2,000 rows of each sample; `cve_ids` was `UNKNOWN` in 1,996 train and 1,991 test rows. Predicted CWE values include `CWE-703` (584 train, 565 test) and `CWE-Unknown` (312 train, 293 test), alongside other values. These are predictions, not confirmed ground truth. `UNKNOWN` is a value and is not counted as an empty field.

Candidate source columns are `vulnerable_function_source`, `function_code` and `patched_function_source`; candidates for vulnerability labels are `label` / `class`, with `cve_ids`, `cwe_ids` and `predicted_cwe_ids` as related metadata. Train uses `label` and `vulnerable_function_source`, while test uses `class` and `function_code`. Their semantic equivalence and what 0 and 1 mean must be verified before mapping them. The column name `vulnerable_function_source` does not establish that every row is vulnerable.

The sample appears promising for CodeBERT binary vulnerability classification experiments, but is not yet verified as suitable: provenance, licensing, label semantics and accuracy, sampling bias, duplication and train/test leakage require investigation. No complete row counts or class distributions were measured. Zero exact duplicate rows within each sample does not rule out repeated code or cross-split leakage.

Patched source fields alone do not establish patch correctness or reliability outcomes. Separately labeled patch-and-outcome data is needed for supervised patch reliability ranking; its availability has not been established.

Dataset identity, source, license and permitted use remain unknown; no license or source metadata appears among the ZIP entries. Before training, verify these, inspect representative records safely, reconcile schemas, validate label meanings and quality, measure full distributions, and check duplicates and leakage by code and repository. Audit command: `& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" scripts/audit_dataset.py archive.zip`. The script streams CSV rows, limits the sample to 2,000 per entry, and skips entries over 256 MiB.

## Full profiling update

A complete streaming profile found 14,248 train rows and 3,563 test rows. Train label counts are 0: 7,950 and 1: 6,298; test counts are 0: 1,962 and 1: 1,601. Candidate source is empty in 55 train rows and no test rows. Patched source is empty in 101 train and 18 test rows. There are five duplicate train code rows beyond first occurrence, no duplicate test code rows, no conflicting-label exact code groups and no exact candidate-code overlap across the original splits. Label meanings and schema equivalence remain unverified. See [DATASET_PREPARATION.md](DATASET_PREPARATION.md) for method, limitations and blockers. Earlier sample statistics above remain explicitly sampled.

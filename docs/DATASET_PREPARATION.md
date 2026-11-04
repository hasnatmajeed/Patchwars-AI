# Dataset preparation and full profile

Milestone 3B generated provisional raw-label CSVs for local research. They are not approved for model training until the label contract, provenance and rights are verified. No source code was executed.

## Milestone 3B: provisional preparation

The standard-library pipeline streams the ZIP twice without extraction or SQLite. Train uses `vulnerable_function_source` and `label`; test uses `function_code` and `class`. The output columns are `source_code`, `raw_label`, and `source_hash` (SHA-256 of the exact decoded source encoded as UTF-8). Source text and raw labels are preserved. No `group_id` is emitted because repository metadata has not been established as a reliable grouping key.

Rows are counted in mutually exclusive skip categories in this order: missing/whitespace-only source, invalid label (anything other than exact `0` or `1`), conflicting-label hash, original-test overlap for train, then duplicate hash. All rows sharing a hash with conflicting labels across either input split are excluded. For other exact cross-split duplicates, the original test row is retained and train rows are excluded. Repeated hashes within a split retain the first valid row. Original test records remain held out. Train hashes are assigned to validation when the first 16 hexadecimal SHA-256 digits interpreted as an integer are divisible by 10; all other hashes go to train. This deterministic code-hash grouping is approximately 90/10, but does not prevent repository or near-duplicate leakage.

| Measurement | Original train | Original test |
| --- | ---: | ---: |
| Input rows | 14,248 | 3,563 |
| Missing source skipped | 55 | 0 |
| Invalid label skipped | 0 | 0 |
| Conflicting-label rows skipped | 0 | 0 |
| Test-overlap rows skipped | 0 | 0 |
| Duplicate rows skipped | 5 | 0 |

There were zero conflicting hashes. All 3,563 original test rows were retained. Output totals, verified by re-reading all generated CSVs:

| Split | Rows | Raw `0` | Raw `1` |
| --- | ---: | ---: | ---: |
| Train | 12,702 | 7,077 | 5,625 |
| Validation | 1,486 | 869 | 617 |
| Test | 3,563 | 1,962 | 1,601 |

Every recorded hash matched its source on re-read, there were no within-split duplicate hashes, and all three pairwise cross-split hash intersections were zero. These checks do not rule out project, semantic or near-duplicate leakage. Repository grouping reliability, label quality, and split-specific label interpretation remain unresolved. This is provisional raw-label data, not a verified vulnerability-label contract.

Run `.\.venv\Scripts\python.exe scripts/prepare_dataset.py archive.zip --dry-run` for a 100-row-per-split check. For a fresh destination, `.\.venv\Scripts\python.exe scripts/prepare_dataset.py archive.zip --prepare` creates `data/processed/{train,validation,test}.csv`; the directory is excluded by `.gitignore`. Existing output is never overwritten: preserve or move it yourself before rerunning. The command checks disk space, stages under `data` and cleans its staging directory on failure. On this run it estimated 204,007,050 bytes required and observed 25,236,164,608 bytes free; actual CSVs total 45,715,927 bytes. `archive.zip` SHA-256 before and after was `660029f51ae9d6e6265194b01aeabff77b19d105acc03ea85fff8b39f9fbab4f`.

Before CodeBERT training, confirm an authoritative split-specific 0/1 label contract and the reference checksums and applicable dataset and underlying-code rights, then assess repository/near-duplicate leakage and label quality. The [Hugging Face card](https://huggingface.co/datasets/S-AIR-L/PyCode-Vul) declares CC BY 4.0 and requests citation of Karim, Akter and Cuzzocrea, ?A Benchmark Dataset for Code-Level Vulnerability Detection and Analysis,? IEEE BigData 2025, pp. 4237?4246. The supplied Zenodo checksums matched locally but could not be independently checked at Zenodo; do not treat this as an independent license grant.

## Dataset identity and complete label verification (prior investigation)

The two entries were identified by their headers and streamed directly from `archive.zip` in bounded chunks for MD5 and as CSV records for statistics. MD5 is used only for comparison with published file identifiers, not for security. No files were extracted, processed datasets generated, or profiling database created.

| Split | Entry | Uncompressed bytes | Calculated MD5 | Match to supplied Zenodo MD5 |
| --- | --- | ---: | --- | --- |
| Train | `PyCode_Vul- train-set.csv` | 72,631,752 | `7538117c1224cc15a028981efd6b00c9` | Yes |
| Test | `PyCode_Vul test-set.csv` | 19,843,261 | `77e72de497b31054466f92bc3c6aee9d` | Yes |

The reference checksums above were supplied in the task as the values listed on [Zenodo record 19746552](https://zenodo.org/records/19746552). Zenodo was inaccessible to the available web tool, so those reference values could not be independently checked against the record. Subject to their accuracy, the uncompressed CSVs match the cited published files by MD5; this does not establish the ZIP container's identity or chain of custody. MD5 is not collision-resistant against adversarial substitution.

| Full-stream measurement | Train | Test | Combined |
| --- | ---: | ---: | ---: |
| Rows | 14,248 | 3,563 | 17,811 |
| `0` | 7,950 | 1,962 | 9,912 |
| `1` | 6,298 | 1,601 | 7,899 |
| Missing labels | 0 | 0 | 0 |
| Invalid nonempty labels | 0 | 0 | 0 |
| Missing original source (empty or whitespace) | 55 | 0 | 55 |

The [upstream repository](https://github.com/S-AiRLab/-PyCode_Vul-A-Benchmark-Dataset-for-Code-Level-Vulnerability-Detection-and-Analysis) states 17,811 records: 7,899 vulnerable and 9,912 non-vulnerable. **Count-based corroboration**, conditional on the supplied reference checksums being accurate, is therefore `1` = vulnerable and `0` = non-vulnerable. This is an inference from aggregate totals, not an explicitly documented encoding or independent proof that both splits use the same encoding. It does not verify individual labels or source quality. Original values remain unchanged; aggregate counts alone do not establish a verified label contract.

The [Hugging Face card](https://huggingface.co/datasets/S-AIR-L/PyCode-Vul) declares CC BY 4.0 for its dataset and links the Zenodo record. The matching supplied checksums support, but do not independently establish, that these local files are the same publication covered by that card; no separate Zenodo license grant has been verified. Verify the link between the referenced versions and rights in underlying third-party code, and comply with applicable attribution, license-link and change-indication requirements before distribution. The card requests citation of: Tasmin Karim, Mst Shapna Akter, and Alfredo Cuzzocrea, ?A Benchmark Dataset for Code-Level Vulnerability Detection and Analysis,? *2025 IEEE International Conference on Big Data (BigData)*, pp. 4237?4246, 2025.

At the time of this identity investigation preparation was not implemented. See Milestone 3B above for current provisional outputs and remaining blockers.

## Milestone 3A.2: published schema and bounded validation (historical)

**Verified:** the local headers match the split-specific columns in the [Hugging Face dataset viewer](https://huggingface.co/datasets/S-AIR-L/PyCode-Vul), which currently reports a dataset cast error because the column names differ. The normalized source and label mappings are:

| Split | `source_code` | `label` | Optional group metadata |
| --- | --- | --- | --- |
| train | `vulnerable_function_source` | `label` | `repo`, `sha`, `file_path` |
| test | `function_code` | `class` | `repo`, `sha`, `file_path` |

These mappings identify columns; they do not prove both source fields have identical provenance or that the numeric labels have the same meaning in both splits. Group fields are optional in dry-run validation and their suitability as grouping keys is unverified. Original label strings are retained. `0` and `1` interpretations remain **unverified**.

The [upstream GitHub repository](https://github.com/S-AiRLab/-PyCode_Vul-A-Benchmark-Dataset-for-Code-Level-Vulnerability-Detection-and-Analysis) describes 17,811 examples from 15 projects. The previously recorded local split counts total 17,811, and sampled local `repo` values include Django, Airflow, Salt and SQLmap, all named upstream. This makes an association plausible, but does not establish identical records, version or provenance. Local ZIP entries are `PyCode_Vul- train-set.csv` (72,631,752 uncompressed bytes, CRC-32 `ad2d75a5`) and `PyCode_Vul test-set.csv` (19,843,261 bytes, CRC-32 `e64e578f`). These ZIP metadata values were not compared with an authoritative checksum.

The Hugging Face card declares CC BY 4.0 for its published dataset; applicability to this unverified local archive and any underlying code is not established. The [Zenodo record](https://zenodo.org/records/19746552) was supplied as an additional reference but was inaccessible during this investigation; its contents were not independently verified. The accessible upstream description mentions CWE mapping and Bandit-based heuristic analysis, which does not verify numerical label meanings.

Run the safe bounded validation with:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_dataset.py archive.zip --dry-run
```

On the local archive it checked 100 rows per split, found no missing sampled source, and counted 52 `0` and 48 `1` in each split. The dry run checks headers, row widths and sampled binary label strings; it does not verify label semantics, provenance, leakage, or later rows and produces no dataset or database. Preparation remains blocked and no full preparation command exists. Next obtain source/version or checksum evidence, applicable licensing, and authoritative split-specific `0`/`1` definitions, then implement and review preparation with leakage safeguards before running it.

## Milestone 3A.1: bounded schema investigation (historical)

The first 100 records of each CSV were read directly from the ZIP with Python's standard library. These are ordered samples, not representative or full-dataset counts. CSV values are strings; type descriptions below describe observed content, not an enforced schema. Python-like means text contains `def `, `import ` or `class `, not that it was parsed or is safe. Nonempty counts include sentinel values such as `UNKNOWN`.

| Exact column | Train nonempty / 100 | Test nonempty / 100 | Observed type and suitability |
| --- | ---: | ---: | --- |
| `vulnerable_function_source` | 100 | absent | Text; all 100 contain Python markers. Best train original-code candidate by name and content, but the name does not establish each row's vulnerability. |
| `function_code` | absent | 100 | Text; all 100 contain Python markers. Best test original-code candidate, but equivalence to the train field is unverified. |
| `patched_function_source` | 100 | 99 | Text; all nonempty values contain Python markers. Named as patched code, so not a verified original-code substitute. |
| `label` | 100 | absent | Binary-looking strings: 52 `0`, 48 `1`. Candidate train label; meanings unverified. |
| `class` | absent | 100 | Binary-looking strings: 52 `0`, 48 `1`. Candidate test label; equivalence and meanings unverified. |
| `repo` | 100 | 100 | Text repository identifier candidate, not source code; grouping reliability unverified. |
| `file_path` | 100 | 100 | Text path metadata, not source code. |
| `sha` | 100 | 100 | Text revision identifier candidate, not source code. |
| `__source_file` | 52 | 52 | Text input-file metadata candidate, not source code; not a verified project identifier. |
| `cve_ids` | 100 | 100 | Text CVE metadata candidate, not source code or a verified binary label. |
| `cwe_ids` | 100 | 100 | Text CWE metadata candidate; all sampled values are `UNKNOWN`, not verified ground truth. |
| `predicted_cwe_ids` | 65 | 66 | Text CWE prediction candidate, not source code or verified ground truth. |

All non-code fields had zero Python markers in the samples. Source and patched text are identical for 10 train rows labeled `1`, 9 train rows labeled `0`, and 9 test rows of each label; other sampled pairs differ. These comparisons do not establish which label means vulnerable. The similar positions, content and names suggest `vulnerable_function_source`/`function_code` and `label`/`class` as split-specific candidates, but do not prove semantic equivalence.

The profiler already selects these different column names explicitly and the earlier full profile completed. Its printed preparation block is intentional: authoritative schema and label evidence is missing, not a demonstrated parsing bug or incompatible headers. No local authoritative dataset documentation or label definition was found; the archive has only the two CSVs. Obtain the original dataset provider's documentation or a written confirmation identifying both split fields, the meaning of `0` and `1`, and the license. Until then do not generate cleaned datasets or run full preparation. The existing script profiles only; it does not implement dataset generation. Previous temporary profiling directories were not removed during this investigation.

The standard-library profiler `scripts/prepare_dataset.py` streams the two ZIP entries and indexes nonempty exact code strings in a temporary SQLite database on the project drive. It is now explicitly invoked with `.\.venv\Scripts\python.exe scripts/prepare_dataset.py archive.zip --profile`; it can require substantial disk space and is not needed for the dry run. It does not create training files. Exact comparisons preserve code as stored; whitespace-only values are treated as missing. Counts below are complete CSV counts, not samples.

| Measurement | Original train | Original test |
| --- | ---: | ---: |
| Rows | 14,248 | 3,563 |
| Label 0 | 7,950 | 1,962 |
| Label 1 | 6,298 | 1,601 |
| Other or empty labels | 0 | 0 |
| Empty candidate code | 55 | 0 |
| Empty patched code | 101 | 18 |
| Duplicate nonempty source rows beyond first occurrence | 5 | 0 |
| Distinct conflicting-label source strings | 0 | 0 |

Across the original splits there are zero identical nonempty candidate source strings and zero conflicting-label source groups. These facts do not rule out near-duplicates, cross-repository similarities or leakage via repository/commit grouping. `repo`, `sha`, and `file_path` are present and nonempty in every row, but their correctness, uniqueness and suitability for grouping have not been established; sentinel values were not classified as missing.

Original train source/label candidates: `vulnerable_function_source` and `label`; original test candidates: `function_code` and `class`. Both also contain `__source_file`, `cve_ids`, `cwe_ids`, `file_path`, `patched_function_source`, `predicted_cwe_ids`, `repo`, and `sha`. Patched source is incomplete and must not be substituted for the original source without evidence. Predictions and CVE/CWE metadata are not verified binary ground truth. Proposed normalized fields, pending evidence, are `source_code`, `label`, `repo`, `sha`, and `file_path`; no mapping or relabeling has been performed.

Once mappings, label semantics and permitted use are verified, filter missing source and invalid labels, quarantine conflicting labels, deduplicate exact code and keep the original test split held out. Exclude or quarantine any exact train/test overlap. Split only original train at approximately 90/10, preferably by verified repository/project identity; otherwise use a deterministic code-hash grouping and disclose that this does not prevent project or near-duplicate leakage. Report resulting counts and label balance then. Current derived train, validation and test counts are **not generated**, not zero.

CodeBERT training is not ready: independent checksum and rights verification, split-specific label meaning, grouping reliability and label quality need further review. Vulnerability classification labels do not establish patch reliability, and this dataset has no verified patch-outcome labels for training a reliability ranker.

# Experimental neural patch ranker

The advisory ranker compares existing Defender proposals from completed review rounds. It is a research demonstration, not a predictor of real-world patch reliability, security, correctness or functional equivalence. It does not change the conservative static candidate selection and never applies code. It is separate from the CodeBERT raw-label classification pilot.

## Data and labels

[`ml/patch_ranker_examples.json`](../ml/patch_ranker_examples.json) contains eight original, self-contained synthetic groups and 16 manually constructed candidates. Each group states its requirement and records why one alternative was preferred. Labels were assigned from those stated requirements during construction, not copied from the numeric training features. There are no independently verified outcomes, external datasets, or real-world production patches. Rights are limited to these project-authored examples. Many alternatives deliberately retain an unsafe original, making the task much simpler than real patch comparison.

The split is by manually declared example family: six groups (six pairs) train, and two groups (two pairs) validate. Both evaluation groups are disjoint in family and exact original from training. This does not establish absence of conceptual similarity or independently validate generalization. With only two validation pairs, the result is extremely unstable.

## Features and method

Deterministic features describe syntax validity, missing syntax or scans, counts and severity weights of existing Bandit findings, introduced findings, added/removed lines, and changed-line fraction. Missing scans have a separate indicator; none of these signals establishes functional correctness. Bandit operates statically and code is never executed. Values are normalized using training data only.

The model is an 11-input, 8-unit tanh hidden layer followed by a linear score. Training uses the pairwise RankNet objective `-log(sigmoid(score(preferred) - score(other)))` with seeded stochastic gradient descent. This is a nonlinear neural network implemented in the Python standard library; no PyTorch, NumPy, pretrained model or additional runtime package is required. Seed 42, 500 epochs and learning rate 0.02 were used on CPU. Train with `.\.venv\Scripts\python.exe -m ml.train_patch_ranker` from the project root; it runs Bandit on the trusted synthetic examples and writes JSON weights and metrics.

## Actual evaluation

The run recorded final training pairwise loss **0.001368**, training pairwise/top-1 accuracy **6/6 (100%)**, and validation pairwise/top-1 accuracy **1/2 (50%)**. A baseline preferring fewer proposed Bandit findings (ties receive half credit) achieved **83.3%** on training and **50%** on validation. Top-1 and pairwise accuracy coincide here because each group has exactly two candidates. These numbers are exploratory, not a held-out real-world benchmark. Full configuration, group IDs and dataset digest are saved in [`ml/results/patch_ranker_metrics.json`](../ml/results/patch_ranker_metrics.json).

## Runtime and limitations

For a controlled demonstration without a provider, open `/research/neural-ranking` on the running Vite site. The backend endpoint `/api/research/neural-ranking-demo` scans the two predefined `eval_numbers` candidates with Bandit and calculates their scores using the saved model. This is a **training example**, not a held-out or real-world evaluation, and the two synthetic candidates are never mixed with live review rounds. No uploaded source is executed and no provider calls are made.

The backend loads versioned [`backend/app/patch_ranker_model.json`](../backend/app/patch_ranker_model.json) using bounded JSON parsing and validates the feature schema and dimensions. Live reviews require at least two distinct, changed, syntactically valid proposals passing the available finding-target and coarse unrelated-change checks. One eligible candidate is reported visibly as having nothing to compare; identical proposals are not compared. Missing or invalid weights disable ranking gracefully. The separate synthetic demo intentionally compares a candidate that retains its synthetic original, and never injects that candidate into a live review. The review response includes an ordered advisory list with original round numbers and static counts; relative scores are not confidence percentages. Equal scores share a rank. The results page links each candidate to its corresponding round in the code comparison. First-round partial results and the existing conservative selection remain intact.

Independent patch/outcome data with verified rights, meaningful requirements, project-level splits, leakage audits, representative hard negatives, functional evaluation in a suitable isolated environment, calibration and external validation are outstanding. The model must not be used to assert that a patch is safe or correct.

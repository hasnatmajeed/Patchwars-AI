"""Build a source-only submission without traversing local directories."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import argparse

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '.env.example', '.gitignore', 'AGENTS.md', 'PLAN.md', 'README.md',
    'backend/requirements.txt', 'backend/app/__init__.py', 'backend/app/ai_agents.py',
    'backend/app/main.py', 'backend/app/scanner.py', 'backend/app/verification.py', 'backend/app/source_units.py',
    'backend/app/patch_ranker.py', 'backend/app/patch_ranker_model.json', 'backend/app/ranker_demo.py',
    'backend/tests/test_ai_review.py', 'backend/tests/test_api.py',
    'backend/tests/test_verification.py', 'backend/tests/test_configuration.py',
    'backend/tests/test_review_stream.py', 'backend/tests/test_zip_review.py', 'backend/tests/test_source_units.py', 'backend/tests/test_patch_ranker.py', 'backend/tests/test_ranker_demo.py', 'backend/tests/ranker_stream_fixture.py',
    'backend/tests/fixtures/demo/clean.py', 'backend/tests/fixtures/demo/eval_example.py',
    'backend/tests/fixtures/demo/project.zip', 'frontend/index.html', 'frontend/package.json',
    'frontend/package-lock.json', 'frontend/vite.config.js', 'frontend/ui.test.mjs',
    'frontend/src/api.js', 'frontend/src/main.jsx', 'frontend/src/style.css', 'frontend/src/diff.js',
    'frontend/src/navigation.jsx', 'frontend/src/public-pages.jsx',
    'frontend/src/review-progress.jsx', 'frontend/src/simple-review.jsx', 'frontend/src/ranker-demo.jsx', 'frontend/src/workspace-components.jsx', 'frontend/src/scan-report.jsx',
    'ml/requirements.txt', 'ml/train_baseline.py', 'ml/train_codebert.py', 'ml/train_patch_ranker.py', 'ml/patch_ranker_examples.json', 'ml/results/patch_ranker_metrics.json',
    'ml/results/metrics.json', 'ml/results/codebert_metrics.json',
    'kaggle/baseline.ipynb', 'kaggle/codebert.ipynb', 'scripts/audit_dataset.py',
    'scripts/prepare_dataset.py', 'scripts/build_submission.py', 'scripts/check_ai_config.py', 'tests/test_prepare_dataset.py',
    'tests/test_train_baseline.py', 'tests/test_train_codebert.py',
    'docs/CODEBERT_TRAINING.md', 'docs/DATASET_AUDIT.md', 'docs/DATASET_PREPARATION.md',
    'docs/FINAL_DEMO.md', 'docs/KAGGLE_BASELINE.md', 'docs/ML_EVALUATION.md',
    'docs/ML_TRAINING.md', 'docs/SUBMISSION_CHECKLIST.md', 'docs/FINAL_PROJECT_REPORT.md',
    'docs/ARCHITECTURE.md', 'docs/DEMO_GUIDE.md', 'docs/TEST_RESULTS.md', 'docs/PROJECT_STATUS.md', 'docs/NEURAL_PATCH_RANKER.md',
    'docs/demo-live/live-bandit-e2e.py', 'docs/demo-live/live-e2e-scan.png',
    'docs/demo-live/live-e2e-consent.png', 'docs/demo-live/live-e2e-review.png',
    'docs/demo-live/live-e2e-compare-changes.png',
)


def build(output: Path) -> None:
    # Reject symlinks, including parent-directory links, before opening the output.
    for name in FILES:
        path = ROOT / name
        parts = [part.lower() for part in path.relative_to(ROOT).parts]
        if any((part == '.env' or part.startswith('.env.') or part.endswith(('.env', '.key', '.pem'))
                or 'credential' in part or 'secret' in part) for part in parts) and name != '.env.example':
            raise ValueError('Secret paths cannot be included in a submission')
        if any(part.is_symlink() for part in (path, *path.parents) if part != ROOT):
            raise ValueError('Submission paths cannot contain symbolic links')
        if not path.is_file():
            raise ValueError('A submission file is missing')
    with ZipFile(output, 'x', compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New ZIP path (existing files are not overwritten)')
    build(parser.parse_args().output)

# Source submission checklist

- Build a new archive with `.\.venv\Scripts\python.exe scripts\build_submission.py path\to\new-submission.zip`. The builder uses an explicit file allowlist and refuses to overwrite an existing archive. Keep `.env.example` free of credentials; local environment files are excluded. Review source files for secrets before submission.

- Extract the archive to a folder, install Python and frontend dependencies, and follow the Windows setup in [README](../README.md); dependencies are not bundled.
- Hosted AI requires a separately obtained API key and provider configuration. Keep the key private and consent before sending source code.
- Use the synthetic files and rehearsal steps in [FINAL_DEMO](FINAL_DEMO.md). Do not execute the synthetic `eval` example.
- The included ML metrics use unverified raw labels. Dataset provenance, rights, and repository/near-duplicate leakage remain unresolved; the datasets are not included.
- Kaggle reported saving the CodeBERT pilot weights and tokenizer. They are not included here; their presence outside Kaggle has not been independently verified. Obtain them separately only if authorized and available.
- Automatic isolated test execution and a validated real-world patch-reliability ranking model are not implemented. The experimental synthetic-data ranker is advisory only. Generated patches and suggested tests require manual review.

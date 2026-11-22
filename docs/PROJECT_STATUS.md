# Project status

## Implemented

- React/Vite public and workspace routes; Python and ZIP scanning with Bandit.
- Bounded notebook code-cell scanning and finding-focused review, including ZIP-contained notebooks. Magic, shell and otherwise unanalyzable cells are reported as skipped.
- Consent-gated hosted Defender and Challenger, selected ZIP member review, optional bounded refinement, partial results, static verification and read-only diff.
- Root `.env` configuration and a source-only submission allowlist.
- Separate exploratory dataset preparation, TF-IDF/logistic regression and CodeBERT research scripts.
- An advisory neural patch ranker trained on a tiny synthetic demonstration dataset; it does not change candidate selection or establish reliability.

## Tested

Automated checks cover real Bandit scanning with synthetic inputs, ZIP validation and mocked hosted-provider workflows; frontend checks cover rendering, routing and request contracts. See [test results](TEST_RESULTS.md) for the actual final run.

## Not verified

No live provider request was made in this ranker work. Provider availability, credentials, model access and the presenter's complete live demo require manual confirmation. Prior headless browser checks used mocked API responses; they are not evidence of live-provider integration. For the earlier classification datasets, provenance, applicable rights, label meanings and repository/near-duplicate leakage remain unresolved; those saved metrics were not retrained here. The new synthetic ranker's tiny validation results are documented separately.

## Not implemented

Sandboxed functional execution of untrusted/generated code, automatic patch application, a validated real-world patch-reliability ranker, production model deployment and a persistent application database are not implemented. No held-out real-world test accuracy is claimed.

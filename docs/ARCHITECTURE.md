# Architecture

```text
React/Vite -> FastAPI -> Bandit static scan -> findings
                      -> hosted Defender -> proposed source
                      -> Bandit + static comparison
                      -> hosted Challenger -> critique and suggested tests
                      -> optional second round -> results / code diff
```

The browser retains the selected upload and results in memory while navigating. Refresh clears this state. FastAPI accepts bounded multipart Python or ZIP uploads. ZIP metadata and selected member paths are revalidated; archive paths are not extracted. Bandit reads a generated temporary file; neither uploaded nor generated Python is executed. The AI provider receives only the explicitly selected source and necessary review context after consent.

Direct notebooks and notebook ZIP members are parsed as bounded JSON. Only valid standalone Python code cells are scanned; magic, shell, non-Python or invalid cells are reported as skipped. For large source, the selected Bandit finding is rescanned and validated server-side before extracting a complete enclosing AST region under a 6,000-byte limit. Static verification compares that scoped region, not the entire source file or notebook. Notebook outputs and metadata are excluded from the provider request.

`/api/ai-review` returns JSON; `/api/ai-review/stream` runs the same pipeline and emits newline-delimited milestone events followed by a result or error. Progress messages contain fixed stage names, not source or prompts. AI results remain untrusted and require manual review. The app has no confirmed persistent application database.

The separate ML research track prepares raw-label data and runs exploratory TF-IDF/logistic regression and CodeBERT classification experiments. These classifiers are not used by the live scanner. A separate experimental neural ranker trained on synthetic examples can advise on existing proposals; it is not a validated reliability predictor and does not change candidate selection. Isolated test execution is not implemented. The dataset preparation script's temporary SQLite index is a research utility, not an application database.

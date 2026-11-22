# PATCHWARS AI

PATCHWARS AI is a university final-year project investigating Python software security. It includes static detection, AI-generated patch and test proposals, static verification and an experimental synthetic-data patch ranker. Isolated execution and validated patch reliability prediction remain research goals. The prototype uses React and a configurable hosted coding model; a separate exploratory CodeBERT classifier has been trained on Kaggle.

The dark multi-page workspace provides Python, ZIP and notebook scans, scoped consent-based AI review, streamed progress and read-only code comparison. Its homepage illustration is an illustrative workflow, not a live scan result. Unsupported notebook cells and partial scans are reported explicitly.

Uploads accept up to **100 MiB** for Python and notebooks and **500 MiB** for ZIP files. Acceptance is separate from analysis: Python sources over the default 8 MiB analysis budget are reported as skipped; notebooks are parsed incrementally and oversized code cells are reported as skipped. Multipart files spool to the system temporary directory after 1 MiB; ensure adequate free space and configure a suitable temporary directory on E: if desired. A proxy may impose a lower limit. AI context is limited separately to 6,000 bytes.

Multipart spooling uses the operating system temporary directory; ensure it has sufficient free space. On Windows, `TMP` and `TEMP` can be set to an existing writable directory on E: before launching the backend. Temporary multipart files are closed after processing and on parsing failure or cancellation.

AI Results summarizes Defender, Challenger and the neural ranker, with full explanations under **Technical details**. Proposals require manual review and tests are not executed.

Code Review displays the selected Python file or notebook code cell and validated reconstructed proposal, including ZIP members, for sources up to 256 KiB. For larger direct Python uploads, the browser can reconstruct a preview locally up to 8 MiB and 100,000 lines only when both hashes match the backend-validated source and proposal. Otherwise the scoped comparison remains available. The proposal is never applied. B404 import reviews require a related call site within the 6,000-byte AI context budget.

An [experimental neural patch ranker](docs/NEURAL_PATCH_RANKER.md) compares multiple existing proposals using static features. Its visible results include a one-candidate explanation or ranked rounds with links to inspect them. It was trained only on a tiny synthetic demonstration dataset, does not override candidate selection, and is not a security or correctness guarantee.

To demonstrate the saved model without a hosted AI request, start the backend and frontend and open `/research/neural-ranking` on the Vite site. The page displays the locally preferred candidate and both code samples first; raw scores and available static checks remain in expandable details. It scans two fixed, project-authored synthetic candidates and runs local inference. This example is part of the model's training data and is not an independent evaluation or a live review.

Milestone 1 upload inspection is implemented and its 15 tests passed. Milestone 2 adds Bandit scanning for individual Python files and ZIP projects, verified by automated tests. The backend also provides a hosted Defender and Challenger review prototype. The React dashboard connects to the backend. Exploratory raw-label baseline and CodeBERT experiments have run on Kaggle; see the [ML evaluation](docs/ML_EVALUATION.md), [PLAN.md](PLAN.md) and [dataset audit](docs/DATASET_AUDIT.md).

Dataset schema investigation is documented in [dataset preparation](docs/DATASET_PREPARATION.md). A bounded `--dry-run` validates the split column mappings. Provisional raw-label CSVs have been prepared; training remains blocked pending a verified label contract, independent reference and rights checks, and leakage review.

A gated exploratory raw-label baseline was run on Kaggle and is described in [ML training](docs/ML_TRAINING.md); no model has been integrated into production.

For a small Kaggle experiment, see the [Kaggle baseline guide](docs/KAGGLE_BASELINE.md) and [notebook](kaggle/baseline.ipynb). Review the dataset and underlying-code rights before uploading.

The [CodeBERT Kaggle guide](docs/CODEBERT_TRAINING.md) describes the GPU-only exploratory experiment. Raw-label semantics and repository-level leakage remain unverified.

For the synthetic fixtures, five-minute script and demo limitations, see the [final demo guide](docs/FINAL_DEMO.md). Automated API checks use real Bandit and a fake hosted provider; the current verification did not include a live provider request or browser interaction.

Final delivery materials: [project report](docs/FINAL_PROJECT_REPORT.md), [architecture](docs/ARCHITECTURE.md), [demo guide](docs/DEMO_GUIDE.md), [test results](docs/TEST_RESULTS.md), and [project status](docs/PROJECT_STATUS.md). The archive includes the small synthetic ranker dataset and weights, but excludes large datasets, pretrained weights, dependencies and local credentials; install dependencies after extraction.

## Windows PowerShell setup

Open PowerShell and run these commands from the extracted project directory. The example assumes `E:\PatchWars Ai`; replace that path throughout with your extraction location. The first uses a per-user Python 3.11 installation; adjust its path if your installation differs. Skip creating the environment if `.venv` already exists. Dependencies must be installed after extraction.

```powershell
Set-Location 'E:\PatchWars Ai'
& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend\requirements.txt
```

Start the backend after dependencies install:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window, run the tests:

```powershell
Set-Location 'E:\PatchWars Ai'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

`GET /health` reports service status. `POST /api/inspect` accepts one multipart file; inspection checks ZIP metadata without executing code or establishing safety. ZIPs allow at most 5,000 entries, an 8 MiB central directory and 1 GiB declared total uncompressed size by default. Unsupported methods, encrypted entries, unsafe paths, collisions and links are rejected.


`POST /api/scan` accepts one `.py`, `.ipynb` notebook or `.zip` project in the multipart `file` field. For example, with the backend running, use PowerShell:

```powershell
curl.exe -F "file=@example.py" http://127.0.0.1:8000/api/scan
```

The response contains `filename`, `total_findings`, `findings` (test ID, severity, confidence, line number and description), and `scan_status`. A clean result is not a security guarantee. For ZIP projects, the response also includes `scan_type`, `python_file_count`, `findings_by_file` and `file_sizes`; each item in the flat findings list includes `file_path`. ZIPs without Python files are rejected. Project scans have a 120-second total limit and each file has at most 30 seconds. Scanning is static analysis and does not verify project behavior. Bandit must be installed using the requirements command above; scanner failures return 503 and timeouts return 504.

Notebook JSON is parsed incrementally with ijson; code-cell sources retained for analysis share an 8 MiB budget. Large outputs and metadata are not retained as notebook trees. A single JSON scalar can still use memory proportional to its size, up to the notebook limit. Parsing has a 120-second deadline, a 200-cell limit, a 128-level nesting limit and a one-million-event budget. Oversized cells are skipped with their original cell indices. For parsed notebooks, standalone Python cells retain their original zero-based cell indices and one-based finding lines. Magic/shell syntax, non-Python kernels, invalid or empty cells and scanner failures are reported as skipped. ZIP scans report each skipped file and reason. Default ZIP analysis budgets are 8 MiB per source, 128 MiB total source data and 120 seconds; files beyond a budget are skipped. Environment variables PATCHWARS_ZIP_ENTRIES, PATCHWARS_ZIP_UNCOMPRESSED, PATCHWARS_SCAN_SOURCE_BYTES and PATCHWARS_ZIP_SCAN_BYTES may lower or raise the corresponding defaults within hard safety caps. Each scanned source uses a 30-second Bandit timeout. No archive path is extracted and no uploaded code is executed. AI review currently cannot select cells from a notebook above the 8 MiB review-source budget. Static scanning and very large JSON string values can consume substantial memory, and concurrent requests are not globally limited; this prototype is intended for local, single-user use.


## React dashboard

With Node.js and npm installed, open a second PowerShell window after starting the backend:

```powershell
Set-Location 'E:\PatchWars Ai\frontend'
npm.cmd ci
npm.cmd run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). Keep both terminal windows open. Vite proxies `/api` and `/health` to the backend at `127.0.0.1:8000`; use the development server for this integration. `npm.cmd` avoids PowerShell's npm script execution-policy restriction. To check a production build, run `npm.cmd run build` in `frontend`.

On `/scan`, choose a Python file, notebook or ZIP; scanning starts automatically. Measurable upload progress is separate from analysis progress. The scan stream reports completed Python files and notebook cells when the workload is known; ZIP notebook preflight is bounded and progress stays indeterminate if a reliable total cannot be established. A confirmed complete scan briefly shows 100% before Results. On `/results`, select a finding and authorize its review in the consent dialog. An optional second fix is off by default and makes additional provider calls. The backend revalidates the selected source, finding and bounded region. `/ai-review/progress` displays confirmed Defender and Challenger activity for each authorized round, and `/ai-review/results` displays the result. With no findings, the exploration dialog reviews one small analyzed source unit and returns explanatory observations without requesting a patch or refinement. `/code-review` compares original and proposed code. Patches are not applied and suggested tests are not executed.

The Scan Results risk groups use a fixed, mutually exclusive Bandit rule mapping: input and injection B102, B307, B608, B610, B611; system commands B404, B602, B603, B604, B605, B606, B607, B609; secrets and cryptography B105, B106, B107, B303, B304, B305, B324. Other rule IDs remain ungrouped. Each category percentage is its count divided by all reported findings; high severity is independent and may overlap those groups. These are finding proportions, not security probabilities. Coverage is shown only when the response supports it.

The scan report distinguishes analyzed code from skipped content. Notebook cells are scanned separately without inventing execution order; unsupported cells and files are reported. Zero findings apply only to code actually analyzed and do not guarantee security. No AI request is made until the user consents and starts a review. The interface reviews one selected issue at a time; returning to Scan Results allows selecting another issue from the same scan. A region that exceeds the server's safe context limit can be rejected.

The public website has separate routes for Home (`/`), Features (`/features`), How It Works (`/how-it-works`), About (`/about`), FAQs (`/faq`) and Privacy (`/privacy`). The application uses `/scan`, `/results`, `/ai-review`, `/ai-review/progress`, `/ai-review/results` and `/code-review`. Navigation and browser Back/Forward preserve the selected File and analysis in memory; refreshing clears them and prompts you to select and scan the file again. The browser cannot restore a local File after reload. Source and results are not stored in browser storage or URLs. Navigating away while a request is active keeps that single bounded request in the current page session; returning to progress does not create another. Closing or refreshing the page interrupts the connection; retry requires an explicit action.

Vite's development server serves the application for direct route visits. A static production host must rewrite requests for these client-side routes to `index.html` while serving actual assets normally and forwarding `/api/*` and `/health` to FastAPI. Without this SPA fallback, refreshing a nested route can return a host 404. Unknown client-side routes show the site's Not Found page.

### Manual browser check

With the backend and Vite running as above, open the Vite URL. This browser interaction has not yet been verified automatically.

1. Choose a small `.py` file containing `eval(input())`; scanning starts automatically and the findings should include Bandit `B307`. Do not execute the file.
2. Scan a clean Python file such as `def add(a, b): return a + b` and check the no-findings message. A clean scan is not a security guarantee.
3. Scan a ZIP containing two Python files and check that their findings appear in one list with file locations. Try an unsupported or oversized file to check the validation message.
4. For a Python file, check the AI consent notice. With no provider configured, consenting and selecting **Run AI review** should report that hosted AI configuration is missing or invalid. A real review requires the provider setup below.
5. Rehearse keyboard navigation and the layout at 360 px, tablet and desktop widths. With an authorized provider, check the automatically selected first issue, consent, single-round and optional refinement results, coverage details, code views, copy controls, and partial-result messages.

For frontend rendering and request-contract checks, run `node --test ui.test.mjs` from `frontend`. The suite also invokes the project `.venv` Python for a mocked backend-to-frontend streaming integration test. These checks do not replace a browser rehearsal.

The API health, single-file and ZIP scans, and Vite proxy were smoke-tested locally. The user reports a successful browser B307 scan and live Defender and Challenger responses; no live provider request or browser interaction was performed in the final verification session.

## Hosted AI review

`POST /api/ai-review` accepts a UTF-8 `.py`, `.ipynb` or ZIP in multipart field `file` and requires the header `X-AI-Consent: true` for each request. For ZIPs, add multipart field `member` with one ZIP-relative source path. The server revalidates the archive and selected member, reads and scans that member, and returns its path as `selected_file`; no other ZIP source is sent to the provider. Consent authorizes sending the selected source scope and relevant Bandit findings to the configured hosted provider; the Challenger also receives the proposed source. Review the provider's handling of source code before using this endpoint. The proposed code is limited to 32 KiB and input context is bounded as described below. The server never executes uploaded or generated code and does not apply patches.

Direct and ZIP-contained notebooks are also accepted for AI review when the multipart `cell` field specifies a zero-based eligible code-cell index. `finding_line` optionally selects a one-based Bandit finding line. `finding_id` may also specify its Bandit rule to distinguish findings on the same line. The server rescans and verifies that finding, then extracts a complete enclosing definition or top-level statement, dedents it and returns its original range in `scope`. The scope must be at most 6,000 UTF-8 bytes and the serialized original context plus findings at most 12,000 bytes. Sources over 6,000 bytes require a finding selection; oversized enclosing regions are rejected rather than silently cut. These are conservative byte limits, not a guarantee that a dynamically routed model has sufficient context or output capacity. If no suitable finding exists, AI review of that large source is unavailable. Notebook metadata and outputs are not sent. Scope-relative findings and diff lines start at 1; use `scope.start_line` to map to the file or cell. A scoped replacement is not a complete file or notebook patch, and its static verification does not establish whole-file correctness.

Challenger and refinement inputs have a separate 24,000-byte serialized context budget. If a proposal or feedback makes that budget too large, the earlier valid proposal is preserved as a partial result instead of making the oversized provider call.

Restart the backend after updating the source: an older running backend can reject the newer finding selection fields even when a file is present. The website uses `POST /api/ai-review/stream` with the same multipart fields and consent/refinement headers. It sends newline-delimited JSON stage events and one final result or safe error event, using the same review pipeline as the synchronous endpoint. Stage events contain no source, prompt or patch. Percentages represent confirmed milestones rather than token generation or estimated time; partial results do not reach 100%. A proxy should allow streaming responses without buffering. If streaming is unavailable the interface remains indeterminate until a result arrives; it never repeats the request automatically.

Create a project-root `.env` by copying `.env.example` and fill in `AI_BASE_URL`, `AI_API_KEY` and `AI_MODEL` locally. Use an HTTPS OpenAI-compatible base URL (typically ending in `/v1`, without `/chat/completions`) and a model supporting chat completions with JSON text responses. The backend reads this file regardless of its working directory. Non-empty process environment variables take precedence; empty or missing variables fall back to `.env`. Keep credentials out of `.env.example` and source control.

To diagnose OpenRouter credentials, run `.\.venv\Scripts\python.exe scripts\check_ai_config.py`. It reports configuration status and key length without printing the key, then checks OpenRouter's key endpoint when the configured base URL or key identifies OpenRouter. A successful key check does not verify model access or chat completions. The diagnostic reads the same effective settings as the backend; values from `.env` are not copied into PowerShell environment variables.

```powershell
Set-Location 'E:\PatchWars Ai'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell session, explicitly consent and submit a file:

```powershell
curl.exe -H "X-AI-Consent: true" -F "file=@example.py" http://127.0.0.1:8000/api/ai-review
```

The JSON response includes `filename`, `original_code`, `original_findings`, `proposed_code`, `defender_explanation`, `challenger_feedback`, `suggested_tests`, `bandit_before`, `bandit_after`, and `manual_review_required` (always true). Suggested tests are descriptions and are not run. Scanner findings before and after are static analysis, not proof that the patch is secure or preserves behavior. Uploaded code and provider responses are untrusted; model instructions direct agents to ignore embedded instructions, but prompt injection cannot be guaranteed to be prevented. Review the returned code and tests manually.

When the selected scope has a Bandit finding, Defender receives the specific issue and proposes a patch; Challenger receives that proposal and the available static checks, then identifies risks and suggests tests. When no finding is reported, optional consented AI analysis is explanatory only: no patch or refinement is requested. Zero findings do not prove security. For example, replacing `eval` with `ast.literal_eval` may reduce a finding while rejecting arithmetic expressions such as `"2 + 3"` that the original accepted. There is no functional execution or production patch-reliability predictor. The exploratory TF-IDF/logistic baseline and CodeBERT validation accuracies were 84.93% and 82.37%, respectively, with unverified raw labels; see [ML evaluation](docs/ML_EVALUATION.md) for macro F1, balanced accuracy and limitations.

The response also includes `verification`, a static report with syntax validity, whether the source changed, finding counts, remaining and introduced findings, line change counts, a status and `manual_review_required`. `static_improvement` additionally requires that the targeted Bandit rule is no longer reported and no obvious changes outside the targeted top-level statement are detected; it is not a security or functional regression test. The unrelated-change check cannot detect all unrelated modifications, especially inside the same function or class, and an absent rule is not proof of repair. Finding matching uses Bandit's test ID, line number and description, with duplicate occurrences counted; moved lines or changed descriptions can be classified as new, and coincidental matches can hide changes. Line additions and removals compare line-text counts, so moved lines are not counted as changes. `no_static_improvement` covers unchanged code, equal or increased counts, or introduced findings. `invalid_patch` covers invalid, empty or oversized proposals; `verification_incomplete` means a required scan is unavailable. Invalid Defender responses still return 502; original scanner failures return 503/504. No code or suggested tests are executed and patches are not applied.

Refinement is optional and off by default. Select **Refine once** in the dashboard or send `X-AI-Refine: true` alongside `X-AI-Consent: true`. This sends the original source and findings, first proposal, Challenger feedback and a bounded verification summary to the provider, then sends the revised proposal for another Challenger review. It adds two provider calls, may incur additional usage or cost, and can take longer. Each request permits at most two rounds and four logical provider calls. Each provider call has one attempt; retrying a failed review requires an explicit user action. The HTTP client uses a 45-second inactivity timeout and 10-second connection timeout, with a 100-second overall limit per provider operation; Bandit retains its 30-second limit per scan. Defender requests at most 8,192 output tokens and Challenger 4,096; providers may apply different limits or count reasoning tokens. Source and proposal limits remain 32 KiB, provider responses 192 KiB, feedback 12,000 characters, and findings 100 / 48 KiB.

The original top-level fields describe round 1. Completed rounds retain their existing fields. If Defender succeeds but the proposed-code scan or Challenger fails, the endpoint returns HTTP 200 with `review_status: partial`, `review_failure` (stage, category and safe message), and the valid proposal in a partial round. Unavailable `bandit_after`, `challenger_feedback` and `suggested_tests` are `null`, not fabricated results; the verifier reports incomplete when the scan is unavailable. If refinement was requested it is `not_started`. Callers must check `review_status` and handle nullable fields. Failures before a valid proposal still use HTTP errors. For a completed first round, `refinement_status` is `not_requested`, `completed`, or `partial`; a second-round failure preserves round 1 and reports a safe `refinement_failure` category. `final_candidate_round` selects the completed static improvement with the fewest proposed findings, preferring the earlier round on a tie; it is null for an incomplete first round or when no candidate qualifies. This comparison is not a verified secure winner, functional test, or reliability score.

Missing consent or invalid uploads return 400/413/415; missing or invalid provider configuration returns 503; provider failures or invalid output before a proposal return 502; provider or original-scan timeouts return 504. Provider text may contain a single unambiguous JSON object surrounded by prose or Markdown fences, but malformed, ambiguous, truncated, empty or schema-invalid output is rejected. A provider's explicit length finish reason is treated as truncation; without that metadata the cause of malformed output remains uncertain. Server warnings record stage, category, attempt, HTTP status, an allowlisted finish reason and observed visible-output byte count when available, plus empty/truncated flags. They omit source, prompts, provider bodies and credentials; the visible-output count does not measure hidden reasoning tokens. No provider call is made without explicit consent.

Defender syntax failures use the safe `invalid_python` category; missing or invalid required fields use `schema_validation`. Round-two failures are labeled with a `round2_` stage in diagnostics. Syntax validation cannot establish that a scoped replacement is complete, behaviorally correct, or secure.

Round 2 Defender receives the original source scope, the target finding, Patch 1, Challenger feedback, and a compact static verification summary. Its two prompt messages have a combined 24,000-byte limit. If the provider reports a length stop, the review retains Patch 1 and leaves ranking unavailable when only one candidate qualifies. Local diagnostics record the requested output cap, prompt size, and token counts when the provider supplies them.

The review screen distinguishes authentication or access denial, billing, quota, rate limits, timeout, invalid output and unavailable-provider errors. A 429 is classified as quota exhaustion only when a bounded, uncompressed error body contains a recognized quota or credit marker; otherwise it remains a rate limit. Explicit quota and billing failures are not retried automatically. Replacing a key means updating local configuration and restarting the backend; do not paste credentials into the interface.

Presentation update: AI Results now summarizes Defender, Challenger and the ranker, with diagnostics under Technical details. Code Review shows a validated complete original and reconstructed proposal for the selected Python file or notebook code cell, including ZIP members, when that source is at most 256 KiB. Larger direct Python uploads can also use the hash-verified local preview described above. Proposals are never applied or executed; both the replacement and reconstructed Python are checked before acceptance.

The final review workflow separates severity percentages from mutually exclusive issue types and places Bandit identifiers and confidence under each issue's Technical details. Code Review defaults to the complete selected source when the validated preview is available, and otherwise displays the scoped diff immediately. The frontend suite covers the current review presentation; browser rehearsal is still recommended.

The Code Review page presents actual model preference scores and proposal cards before the original/proposed diff. Patch buttons select the corresponding review round; scores are advisory and are not probabilities. Equal scores do not select a winner.

AI Results uses the same ranker and proposal cards as Code Review. Local preview reconstruction never sends the full file to the hosted AI service.

Optional Round 2 requests a distinct, targeted alternative when justified; returning the original or repeating Round 1 is identified separately and is not treated as a distinct ranking candidate. The request does not add provider retries or guarantee another patch.

Zero-finding scans use a compact coverage summary, and exploratory reviews show AI observations and suggested checks without a patch or ranking. Coverage percentages are displayed only when the response supplies a valid denominator; exploratory suggestions are not executed or confirmed findings.

For the final verification results and instructions to rebuild the source submission ZIP, see the [test results](docs/TEST_RESULTS.md) and [submission checklist](docs/SUBMISSION_CHECKLIST.md).

AI Results shows up to three excerpts per agent, with the complete responses in Technical details. In Code Review, the comparison toolbar groups round selection, source scope, copy actions, and Split or Unified views. The ranker displays raw scores when it has comparable eligible proposals.

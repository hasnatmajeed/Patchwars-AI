# PATCHWARS AI

PATCHWARS AI is a university final-year project investigating Python software security. Planned features include static detection, AI-generated patches and security tests, isolated verification, and patch reliability ranking. The prototype uses React and a configurable hosted coding model; PyTorch and CodeBERT are not implemented.

Milestone 1 upload inspection is implemented and its 15 tests passed. Milestone 2 adds Bandit scanning for individual Python files and ZIP projects, verified by automated tests. The backend also provides a hosted Defender and Challenger review prototype. The React dashboard connects to the backend. An exploratory raw-label baseline has been run on Kaggle; CodeBERT training remains pending. See [PLAN.md](PLAN.md) and the [dataset audit](docs/DATASET_AUDIT.md).

Dataset schema investigation is documented in [dataset preparation](docs/DATASET_PREPARATION.md). A bounded `--dry-run` validates the split column mappings. Provisional raw-label CSVs have been prepared; training remains blocked pending a verified label contract, independent reference and rights checks, and leakage review.

A gated exploratory raw-label baseline was run on Kaggle and is described in [ML training](docs/ML_TRAINING.md); no model has been integrated into production.

For a small Kaggle experiment, see the [Kaggle baseline guide](docs/KAGGLE_BASELINE.md) and [notebook](kaggle/baseline.ipynb). Review the dataset and underlying-code rights before uploading.

The [CodeBERT Kaggle guide](docs/CODEBERT_TRAINING.md) describes a prepared GPU-only exploratory experiment. Raw-label semantics and repository-level leakage remain unverified.

## Windows PowerShell setup

Open PowerShell and run these commands from the project directory. The first uses the verified Python 3.11 installation; adjust its path if your installation differs. Skip creating the environment if `.venv` already exists.

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

`GET /health` reports service status. `POST /api/inspect` accepts a multipart upload in the `file` field. Inspection checks ZIP metadata only; it does not execute code or establish whether code is safe. Uploads are limited to 10 MiB, ZIPs to 100 entries and 50 MiB declared uncompressed size. The local environment and dataset remain on E:.


`POST /api/scan` accepts one `.py` file or `.zip` project in the multipart `file` field. For example, with the backend running, use PowerShell:

```powershell
curl.exe -F "file=@example.py" http://127.0.0.1:8000/api/scan
```

The response contains `filename`, `total_findings`, `findings` (test ID, severity, confidence, line number and description), and `scan_status`. A clean result is not a security guarantee. For ZIP projects, the response also includes `scan_type`, `python_file_count`, and `findings_by_file`; each item in the flat findings list includes `file_path`. ZIPs without Python files are rejected. Project scans have a 120-second total limit and each file has at most 30 seconds. Scanning is static analysis and does not verify project behavior. Bandit must be installed using the requirements command above; scanner failures return 503 and timeouts return 504.


## React dashboard

With Node.js and npm installed, open a second PowerShell window after starting the backend:

```powershell
Set-Location 'E:\PatchWars Ai\frontend'
npm.cmd install --cache 'E:\PatchWars Ai\.npm-cache'
npm.cmd run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). Keep both terminal windows open. Vite proxies `/api` and `/health` to the backend at `127.0.0.1:8000`; use the development server for this integration. `npm.cmd` avoids PowerShell's npm script execution-policy restriction. To check a production build, run `npm.cmd run build` in `frontend`.

Select a `.py` file or `.zip` project and choose **Run security scan**. Selection alone does not upload the file. The dashboard shows Bandit findings grouped by file; a clean result is not a security guarantee. For AI review, scan a Python file no larger than 32 KiB, configure the hosted provider in the backend terminal as described below, then select the consent checkbox and **Run AI review**. Source code and findings are sent to that third party. AI review requires a real configured provider; the static scanner works without one. Review proposals manually; the dashboard does not apply patches or execute suggested tests.

### Manual browser check

With the backend and Vite running as above, open the Vite URL. This browser interaction has not yet been verified automatically.

1. Confirm the header says **Backend connected**. Choose a small `.py` file containing `eval(input())` and click **Run security scan**; the findings should include Bandit `B307`. Do not execute the file.
2. Scan a clean Python file such as `def add(a, b): return a + b` and check the no-findings message. A clean scan is not a security guarantee.
3. Scan a ZIP containing two Python files and check that findings are grouped by file. Try an unsupported or oversized file to check the validation message.
4. For a Python file, check the AI consent notice. With no provider configured, consenting and selecting **Run AI review** should report that hosted AI configuration is missing or invalid. A real review requires the provider setup below.

The API health, single-file and ZIP scans, and Vite proxy were smoke-tested locally; the user also reports a successful browser B307 scan. The AI provider has not been verified live.

## Hosted AI review

`POST /api/ai-review` accepts one UTF-8 `.py` file in multipart field `file` and requires the header `X-AI-Consent: true` for each request. Consent authorizes sending the source and Bandit findings to the configured hosted provider; the Challenger also receives the proposed source. Review the provider's handling of source code before using this endpoint. ZIP projects are not accepted by this endpoint; select one Python file. Input and proposed code are limited to 32 KiB. The server never executes uploaded or generated code and does not apply patches.

Configure an HTTPS OpenAI-compatible base URL (typically ending in `/v1`, without `/chat/completions`), API key and model in the PowerShell session that starts the server. `.env.example` lists the variable names; the application reads environment variables and does not automatically load that file. Use a provider endpoint and model that support chat completions with JSON text responses.

```powershell
Set-Location 'E:\PatchWars Ai'
$env:AI_BASE_URL = 'https://YOUR_PROVIDER_HOST/v1'
$env:AI_API_KEY = 'YOUR_API_KEY'
$env:AI_MODEL = 'YOUR_MODEL'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell session, explicitly consent and submit a file:

```powershell
curl.exe -H "X-AI-Consent: true" -F "file=@example.py" http://127.0.0.1:8000/api/ai-review
```

The JSON response includes `filename`, `original_code`, `original_findings`, `proposed_code`, `defender_explanation`, `challenger_feedback`, `suggested_tests`, `bandit_before`, `bandit_after`, and `manual_review_required` (always true). Suggested tests are descriptions and are not run. Scanner findings before and after are static analysis, not proof that the patch is secure or preserves behavior. Uploaded code and provider responses are untrusted; model instructions direct agents to ignore embedded instructions, but prompt injection cannot be guaranteed to be prevented. Review the returned code and tests manually.

Missing consent or invalid uploads return 400/413/415; missing or invalid provider configuration returns 503; provider failures or invalid output return 502; provider or scanner timeout returns 504. Requests use bounded sizes and timeouts and at most two attempts per provider call for transient failures. No provider call is made without explicit consent.

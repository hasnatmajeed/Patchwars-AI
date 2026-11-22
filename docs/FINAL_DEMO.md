# Final demonstration guide

This prototype combines Bandit static analysis with optional hosted AI review. It does not execute uploaded code or suggested tests, apply patches, or provide a trained patch-reliability score. Use only source you are allowed to send to the configured provider. The demo files below are synthetic; do not run them.

## Start the application on Windows

The commands assume `.venv` and frontend dependencies are installed as described in the [README](../README.md). Replace `E:\PatchWars Ai` with the extracted project directory if different. Open PowerShell:

```powershell
Set-Location 'E:\PatchWars Ai'
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell window:

```powershell
Set-Location 'E:\PatchWars Ai\frontend'
npm.cmd run dev
```

Open the local address printed by Vite, normally `http://localhost:5173`. Keep both windows open and check for **Backend connected**. If it is offline, check the backend window and port. The dashboard uses Vite's proxy to reach FastAPI.

## Hosted AI configuration

For AI review, configure an authorized HTTPS OpenAI-compatible provider and model in the **backend's PowerShell session before starting FastAPI**. Use a provider and account approved for the source being sent. Source and findings are sent to the provider; the proposal is also sent for Challenger review. Do not paste a key into a document, screenshot, chat, or shared terminal. For example, enter the key in the password field of the credential prompt:

```powershell
$env:AI_BASE_URL = 'https://openrouter.ai/api/v1'
$env:AI_MODEL = 'YOUR_MODEL'
$demoCredential = Get-Credential -UserName 'api-key' -Message 'Enter your hosted AI API key as the password'
$env:AI_API_KEY = $demoCredential.GetNetworkCredential().Password
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Use the provider's correct base URL and model, and run this from the project root. Restart the backend after changing its environment. The key is available to that process; close the terminal after the demo. If configuration is missing, AI review reports an error and scanning still works. A provider can also fail, time out, or reject a request. No live provider request was made during this verification session; the user previously reported a successful live review.

OpenRouter may also return truncated output; the application performs a bounded Challenger retry and preserves a valid Defender proposal if later review fails. Defender proposes and explains a change; Challenger critiques it and suggests tests. **Refine once** defaults off and, when selected with consent, requests a second round. Static improvement does not establish preserved behavior: replacing `eval` with `ast.literal_eval` may reject arithmetic expressions such as `"2 + 3"`.

## Demonstrate the workflow

1. Open **Scanner**, select `backend\tests\fixtures\demo\clean.py` and click **Start scan**. Expect no Bandit findings; this does not prove the file is secure.
2. Select `backend\tests\fixtures\demo\eval_example.py` and scan. Expect `B307`, severity `MEDIUM`, line 1. Explain that Bandit flags use of `eval`; it reports a static finding rather than executing the source.
3. Select `backend\tests\fixtures\demo\project.zip` and scan. Show the two file groups: the clean file and the B307 example. ZIP review is scanning only; AI review accepts individual Python files.
4. Re-select and scan `eval_example.py`. Open **AI Battle**, read the third-party disclosure, check the consent box only if you authorize the transfer, and click **Run AI Battle**. Wait for the loading state. Defender's result shows the proposed code and explanation. The proposal has not been applied.
5. Open **Code Review** to show the original and proposal, and the **before** and **after** Bandit findings. A reduction in findings is not proof of security or preserved behavior. Provider output and findings may vary.
6. Show the **Challenger** panel and its suggested tests. The tests are descriptions and have **not been executed**. Manually review the proposal and feedback; do not run generated code during the demonstration.

The dashboard has loading and error messages and responsive layout rules, but the current session did not perform browser interaction or visual checks. Rehearse these steps and test a narrow window before presenting. The API tests use synthetic inputs, real Bandit, and a fake HTTP provider; they do not validate a live provider or browser rendering.

## Present the ML results

Use [ML evaluation](ML_EVALUATION.md): both experiments trained on 2,000 examples and evaluated 1,486 validation examples with unverified raw labels. The Kaggle CPU TF-IDF/logistic baseline achieved 84.93% accuracy, 84.12% macro F1 and 83.52% balanced accuracy. One-epoch CodeBERT on a Kaggle T4 achieved 82.37%, 80.54% and 79.45%, respectively. CodeBERT did not improve these metrics. Neither is validated for production security claims; neither is a patch-reliability ranking model.

## Five-minute script

| Time | Action and explanation |
| --- | --- |
| 0:00–0:30 | Introduce the prototype and confirm the backend is connected. |
| 0:30–1:30 | Scan the clean file and the B307 example; point out severity and line number. |
| 1:30–2:00 | Scan the ZIP and show findings grouped by file. |
| 2:00–3:30 | Scan the Python example again, give consent, and show Defender, before/after findings and Challenger. If the provider fails, state the error; do not present a fake response as live. |
| 3:30–4:15 | Present the baseline and CodeBERT validation numbers and their raw-label qualification. |
| 4:15–5:00 | Explain manual review, unexecuted tests, the absence of isolated execution and the limitations of synthetic-data patch ranking, and invite questions. |

## Likely examiner questions

- **Does fewer Bandit findings mean the patch is secure?** No. Static analysis has limited coverage and does not establish behavior or security.
- **Were Challenger's tests run?** No. They are suggestions for a human; there is no isolated execution system in this prototype.
- **Does CodeBERT rank patches?** No. It is an exploratory raw-label classifier, not a patch-outcome ranker.
- **Why did CodeBERT score lower?** One epoch, a small ordered training subset, truncation and hyperparameters are possible factors; the experiment does not establish the cause.
- **Can the metrics be trusted for deployment?** No. Label meanings, provenance, rights and repository/near-duplicate leakage remain unresolved; validation results are exploratory.

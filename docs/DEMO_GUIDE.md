# Presentation demo

The successful live review used `live-bandit-e2e.py`. A copy of that exact synthetic input is in [demo-live](demo-live/live-bandit-e2e.py). Upload it for static analysis; **do not execute it**. Bandit should report B307 for `eval` on line 2.

Prepare the project environment and frontend dependencies as described in the [README](../README.md). Configure `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` in the project-root `.env`; keep the key private. Before presenting, check ports 8000 and 5173 and confirm the provider configuration:

```powershell
Set-Location 'E:\PatchWars Ai'
netstat -ano -p tcp | Select-String ':(8000|5173)\s.*LISTENING'
.\.venv\Scripts\python.exe scripts\check_ai_config.py
```

An occupied port may belong to another process: confirm its identity before using it or choose different ports and configure the Vite proxy accordingly. A successful credential check does not guarantee model availability or a successful review. Start the services in separate terminals:

```powershell
# Terminal 1, from the project root
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2
Set-Location 'E:\PatchWars Ai\frontend'
npm.cmd run dev
```

Open the Vite URL, normally `http://localhost:5173`. The default Vite proxy expects the backend on port 8000.

1. **Upload and scan:** choose `docs/demo-live/live-bandit-e2e.py`. Scanning starts automatically. Show the B307 finding and select **Review with AI**.
2. **Authorize:** explain that the selected code and findings are sent to the configured provider. Check the consent box. To request a second candidate, also check **Try a second fix**, then start the review. Refinement is optional and makes additional provider calls.
3. **Defender and Challenger:** show the actual proposal and review for the selected round. Discuss any reported concerns; do not claim that a patch is secure or that suggested tests ran.
4. **Neural Patch Ranker:** if two distinct eligible candidates are returned, show their raw model scores and the preference or tie. The score is not a security probability. Results and eligibility can differ between runs.
5. **Code comparison:** use **View Original Code**, **View Proposed Patch**, and **Compare Changes** to inspect the original, selected proposal, and diff. The proposal is not automatically applied; tests are not executed.

If OpenRouter fails, show the actual error and explain that the live review could not be completed. Check connectivity, credentials and model availability without revealing secrets; retry only when appropriate. If only one eligible patch is returned, show the available proposal and the truthful ranking-unavailable message; do not claim a comparison or winner. A refresh clears the in-memory review, so rescan to restart.

The following captures are from the earlier successful live run and are a **recorded backup**, not the current result: [scan](demo-live/live-e2e-scan.png), [consent](demo-live/live-e2e-consent.png), [review and ranking](demo-live/live-e2e-review.png), and [code comparison](demo-live/live-e2e-compare-changes.png). The ranker is experimental and all proposals require human review.

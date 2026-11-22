# Test results

## Final submission verification

The full Python suite passed **245**, failed **0**, and skipped **2** baseline training tests because scikit-learn was unavailable. It reported three warnings, one Starlette test client deprecation and two duplicate ZIP fixture warnings. The frontend suite passed **83** with no failures or skips, and the Vite production build succeeded.

The final checks combine this automated rerun with the prior browser pass. The recorded browser completion view shows 100% with all three scan units retained for a mixed ZIP. Automated checks cover scan failures, mocked provider responses, partial results, patch eligibility, ranking and code-view actions. Hosted-provider availability was not retested during final packaging.

## Neural ranking research demo

The full Python suite passed **206**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**, using temporary storage on E:. The frontend suite passed **40**, failed **0**; the Vite production build passed. A real local endpoint calculated the saved model's outputs for two fixed synthetic candidates. A headless Chrome check displayed that endpoint's actual response at 360 and 1366 pixels without document overflow; both screenshots were visually inspected. No hosted provider calls or saved-model retraining were performed.

## Round-two refinement reliability

The full Python suite passed **204**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**, using a fresh temporary directory on E:. An initial run using the nearly full C: system temporary drive failed three unrelated tests with insufficient disk space. The frontend suite passed **39**, failed **0**; the Vite production build passed. Mocked provider tests cover refinement JSON, required-field and Python syntax failures, truncation retry limits, source and feedback preservation, partial results and two-candidate ranking. No live provider request or model retraining was performed.

## Visible neural ranking integration

The complete Python suite passed **197**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**. The frontend suite passed **38**, failed **0**, and the Vite production build passed. A mocked-provider integration test feeds the actual FastAPI streaming response through the frontend stream parser and result component for one and two rounds. A headless browser check additionally exercised shared state and navigation to the selected round, with consent and optional refinement. Stream tests cover selected notebook cells, ZIP-contained notebooks and bounded finding scopes. Equal-score proposals share a rank. No live provider calls or model retraining were performed.

## Synthetic neural ranker

Training ran locally on CPU with 6 training and 2 validation synthetic pairs; final training loss was 0.001368 and validation pairwise/top-1 accuracy was 1/2. The full Python suite passed **192**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**. The frontend suite passed **36**, failed **0**, and the Vite production build passed. Provider calls were mocked. These tiny synthetic results do not establish real-world patch reliability; see [neural ranker details](NEURAL_PATCH_RANKER.md).

Final verification independently reproduced the saved weights and metrics in memory from the recorded dataset and confirmed its SHA-256 and declared family split. Two synthetic review candidates produced finite scores with their round identifiers; one candidate returned `single_candidate` with no ranking. The complete Python suite again passed **192**, skipped **2**, with **3 warnings**; the frontend suite passed **36** and the production build passed. No live provider request was made.

## Unified scan results

The complete Python suite passed **188**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**. The frontend suite passed **35**, failed **0**; the Vite production build passed. A headless Chrome test used a synthetic notebook and mocked responses to verify automatic scan, a single AI action, consent, the selected cell and finding, and the outside-review notice. No live provider calls were made.

## Simplified AI review results

The full Python suite passed **188**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**. The frontend suite passed **34**, failed **0**; the Vite production build passed. Headless Chrome displayed a synthetic, mocked review at 360, 768 and 1366 pixels without document overflow, and all three screenshots were visually inspected. No live provider requests were made.

## Visual quality repair

Headless Chrome used viewport emulation at 360, 768, 1366 and 1440 pixels to open every public and workspace route. Automation checked document overflow, mobile menu opening and closing, CTA text color, workflow spacing, and a synthetic scan through mocked AI results and code comparison. Full-page screenshots of Home, How It Works, About, Scan Results, AI Results and Code Review were captured; selected desktop and mobile images were visually inspected. Review responses were mocked and no live provider calls were made. This is not a complete keyboard, screen-reader or contrast audit.

The complete Python suite passed **188**, failed **0**, skipped **2** (scikit-learn unavailable), with **3 warnings**. The frontend suite passed **33**, failed **0**; the Vite production build passed.

## Dark visual rebuild

The full Python suite (`.\.venv\Scripts\python.exe -m pytest -q -rs`) passed **188 tests**, with **2 skipped** (scikit-learn is absent) and **3 warnings**. The frontend suite (`node --test ui.test.mjs`) passed **32 tests** and the Vite production build (`npm.cmd run build`) passed. These checks use synthetic input and mocked providers. A headless Chrome desktop homepage screenshot was inspected; a 360-pixel screenshot was clipped and requires verification with proper mobile viewport emulation. Other routes, interactive behavior, accessibility and live provider use were not visually checked for this rebuild.

## Scan and AI report UX follow-up

The full Python suite passed **181 tests**, with **2 skipped** because scikit-learn is absent and **3 warnings**. The frontend suite passed **30 tests**, and the Vite production build passed. Headless Chrome exercised a mocked partial notebook scan, consent and AI results at 360, 768, 1366 and 1440 pixels without document-level overflow or console errors. The mobile and desktop scan report and desktop AI report were visually inspected; minor subsequent changes were checked by the frontend suite and build. These mocked checks are not a live-provider test or a complete accessibility audit.

## Notebook and scoped review follow-up

The full Python suite (`.\.venv\Scripts\python.exe -m pytest -q -rs`) passed **181 tests**, with **2 skipped** because scikit-learn is absent and **3 warnings**. Frontend tests passed **25 tests** and the Vite production build passed. Tests use mocked providers and synthetic input; no live provider call or current-session browser rehearsal was performed. Large contexts can still exceed provider-specific limits or produce truncated responses.

## Hosted AI JSON resilience follow-up

The follow-up full Python suite (`.\.venv\Scripts\python.exe -m pytest -q -rs`) passed **172 tests**, with **2 skipped** because scikit-learn is not installed and **3 warnings** (one Starlette deprecation and two duplicate-ZIP fixture warnings). The frontend suite (`node --test ui.test.mjs`) passed **23 tests**; `npm.cmd run build` passed. Mock provider tests cover JSON correction within the shared two-attempt limit, streamed errors and partial results. No live provider call was made; the exact format of the reported live response remains unknown.

Final delivery run, 2026-11-14, from the project root unless stated otherwise:

| Check | Command | Result |
| --- | --- | --- |
| Complete Python suite, including archive tests | `.\.venv\Scripts\python.exe -m pytest -q -rs` | **162 passed, 0 failed, 2 skipped, 3 warnings** |
| Frontend tests (from `frontend`) | `node --test ui.test.mjs` | **23 passed, 0 failed, 0 skipped** |
| Production frontend build (from `frontend`) | `npm.cmd run build` | **passed** (Vite 6.4.5) |

Both skipped tests require scikit-learn, which was not installed in the backend environment. The warnings were one Starlette TestClient deprecation and two expected duplicate-ZIP-name warnings from safety tests. Tests use synthetic files and mocked AI provider responses; they do not prove generated patches secure.

Earlier headless Chrome QA checked routes and document overflow at 360, 768, 1366 and 1440 pixels, and exercised mocked Python/ZIP review, selection reset, consent, progress, retry, navigation and mocked clipboard. Those checks were performed before this final packaging run, with mocked API responses; browser interaction and a live provider were not retested in this delivery run. A real provider demo remains a manual check.

A source archive candidate passed ZIP integrity, path and exact-source checks, relative frontend import resolution, and a limited credential-pattern scan. A clean temporary extraction passed backend `/health` using the existing Python environment, and frontend `npm ci --offline --ignore-scripts` plus a production build using the existing npm cache. These checks do not establish that dependencies can be installed on a different machine or that all possible secrets can be detected.

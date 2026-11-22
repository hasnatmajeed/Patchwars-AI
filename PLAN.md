# Roadmap

- **Scan progress and review errors (implemented with limits):** Upload bytes and completed Python files or notebook cells are reported separately. Mixed ZIP workloads use bounded preflight and fall back to indeterminate when a safe total is unavailable; confirmed complete scans show 100% before navigation. Provider failures use a single attempt, and retries require a user action; historical retry notes below describe the superseded behavior.

- **Review routing (implemented):** Finding-specific consent opens streamed Defender/Challenger activity; zero-finding exploration remains a separate consented, patch-free path.

- **Scan Results dashboard (implemented):** Actual Bandit findings are grouped by a documented rule mapping, high priority is reported separately, and finding rows retain per-issue review actions. Percentages describe finding proportions, not security likelihood.
- **Scan Results visual refresh (implemented):** A single panel presents severity counts, three finding-share rows and a coverage row. The primary AI action opens the findings disclosure when the scan has multiple findings and uses the existing consent modal for the chosen issue.

- **Research demo clarity (implemented):** The local model preference and both synthetic code samples are presented first, with raw scores and static details expandable. The demo remains a training example, not an independent validation.

- **Review multipart compatibility (implemented):** Review requires explicit consent and a retained named File; missing-file and older-backend errors are distinguished from provider failures. Python, notebook and ZIP selection payloads are covered by mocked-provider tests. Running backends must be restarted to load updated multipart fields.

- **Finding reselection and unchanged results (implemented):** Each finding can be selected from the existing scan, including same-line rules. Review attempts, changed code and eligible ranking candidates are counted separately; unchanged responses are not labeled fixes.

- **Final results clarity (implemented):** Scan counts, scoped static reduction, proposal and test counts, ranking eligibility, bounded full-source viewing, and B404 import-call context are explicit. Functional reliability remains untested.

- **Scan and review clarity (implemented):** Indeterminate scan feedback and explicit retry use the existing single request; the local synthetic ranker highlights its actual preference and review setup separates exploratory analysis from optional security refinement. Browser and live-provider checks are reported separately.

- **AI review form and upload feedback (implemented):** A focused consent and optional-refinement form explains hosted transfer and zero-finding behavior. The upload form displays the current per-type limits and does not show a ready state after an error.
- **Larger uploads (partial):** Multipart parsing spools 100 MiB Python/notebook and 500 MiB ZIP uploads to temporary storage; ZIP metadata is inspected on disk and analysis is bounded with explicit skipped-file reporting. Large notebooks are incrementally parsed with bounded retained cell sources, JSON depth and event limits; very large individual JSON strings still consume proportional memory. Large-notebook AI review and multi-user resource isolation remain open. Actual boundary verification is described in the delivery report.

- **Patch comparison visibility (implemented):** Code Review displays existing round proposals, experimental ranks and raw scores where available, and recorded exclusion reasons. Switching rounds does not initiate another review or apply code.

- **Finding-grounded review (implemented):** A zero-finding scope receives optional explanatory-only analysis, never an AI patch or refinement. For a reported issue, prompts carry the target and Challenger receives static checks. Distinct candidates are required for advisory ranking; static and coarse unrelated-change checks cannot prove safety or preserved behavior.

- **Neural ranking research demo (implemented):** A separate `/research/neural-ranking` page runs the saved model and local Bandit on a fixed, project-authored training example. It never creates a synthetic candidate in live AI review or calls the hosted provider.

- **Round-two refinement reliability (implemented; live retest pending):** The refinement prompt explicitly uses the original scope, first proposal and critique. A truncated first refinement response may use the existing second-attempt budget with a concise instruction; field and Python syntax failures have distinct safe categories, and round one remains available. Syntax validity cannot establish semantic correctness.

- **Visible neural ranking (implemented):** Results show the one-candidate explanation or experimental ranking rows, including tied scores and links to the corresponding code-review rounds. Mocked backend-to-stream-to-frontend and browser navigation checks cover explicit refinement and consent.

- **Experimental synthetic neural ranker (implemented):** An advisory tanh RankNet compares existing valid review rounds using static features and locally trained JSON weights. Validation is only two synthetic groups; no real-world reliability claim is supported. See `docs/NEURAL_PATCH_RANKER.md`.

- **Unified scan results (implemented):** Python, notebook and ZIP scans show one combined summary and issue list. Optional AI review automatically targets the first finding, requires consent and reports the exact covered and excluded findings. It does not review all project findings; oversized enclosing regions can still be rejected.

- **Simplified AI review results (implemented):** The result page presents the actual outcome, findings count, code change and test execution state first; full explanations and static findings remain in expandable technical details. Partial reviews and scoped notebook or ZIP selections remain explicit.

- **Visual quality repair (implemented):** Corrected CTA contrast and public-card spacing, refined workflow and About layouts, and checked routes at mobile, tablet and desktop sizes with synthetic review data. Live-provider and assistive-technology checks remain manual.

- **Dark visual rebuild (implemented; browser rehearsal pending):** Public pages and the existing scan, streamed review and code comparison workspaces share a navy/cyan design. The original shield illustration is local SVG/CSS; scan coverage and AI results remain based on actual responses. No live provider request was made for this visual milestone.

- **Beginner-focused scan and AI reports (implemented):** Scan results explain zero findings and partial coverage, list actual skipped content, and provide issue/cell-specific review actions. The AI report separates Defender, Challenger and static verification without implying that a scoped patch is a complete-file fix.

- **Provider guidance and visual refinement (implemented; live-provider and browser retest pending):** Safe provider categories distinguish access, quota, billing, rate limits and invalid output, including partial refinement failures. The workspace and public pages clarify scope, consent and manual review. The submission ZIP must be rebuilt after these changes.
- **Bounded finding review and notebooks (implemented; live-provider and browser retest pending):** Bandit scans valid notebook code cells and reports skipped cells; ZIPs include Python and notebook sources. Large inputs require a server-verified finding and a complete bounded AST region. The UI labels scoped proposals and partial scans; provider token limits can still cause failure.

- **Hosted AI JSON resilience (implemented; live retest pending):** Explicit JSON encoding instructions and one format-correction retry share the existing two-attempt limit. Malformed or ambiguous output remains rejected, with schema validation and partial-result preservation unchanged. The reported live formatting defect cannot be determined from metadata alone.

- **Final delivery:** The source allowlist includes the current routed frontend, ZIP review and streaming tests, and delivery documentation. Final automated results and remaining live-demo limitations are recorded in [test results](docs/TEST_RESULTS.md) and [project status](docs/PROJECT_STATUS.md).

- **AI review progress and results (implemented; browser rehearsal pending):** A separate bounded streaming endpoint reports actual pipeline milestones; distinct progress and result pages preserve partial reviews and require explicit retry. The synchronous API remains available; no submission archive was rebuilt.

- **Multi-page website (implemented; browser rehearsal pending):** Public information pages and distinct scan, results, AI review and code review routes use in-memory shared state and browser history. Production static hosts need an SPA fallback and API proxy. No submission archive was rebuilt.

- **ZIP AI review and simplified workspace (implemented; browser rehearsal pending):** ZIP scans list individual Python findings and permit explicit review of one selected file. The backend revalidates the archive and rescans that file; the redesigned workspace retains consent and optional refinement. No submission archive was rebuilt.

- **Local AI configuration (implemented):** The backend reads project-root `.env` settings with non-empty process environment overrides. Submission packaging uses a fixed source-file allowlist; existing archives are not rebuilt automatically.
- **OpenRouter configuration diagnostic (implemented):** A local command reports safe configuration metadata and checks the OpenRouter key endpoint without making a chat completion request.

- **Milestone 0 — Foundation (in progress):** Audit the local dataset and establish repository guidance. A bounded preliminary CSV sample is documented; provenance and full validation remain open. Acceptance: five foundation files exist, dataset facts and uncertainties are recorded, and Git ignore behavior is verified where Git is available.
- **Milestone 1 - Input and backend (completed):** Python and ZIP upload inspection is implemented and tested.
- **Milestone 2 - Static scanning (completed):** Bandit scans Python files and validated ZIP projects; real integration and upload safety tests pass. Findings are static-analysis results, not security guarantees.
- **Milestone 3 — Defender:** After M2, generate candidate patches with a selected coding model. Acceptance: a finding produces a reviewable patch and failures are reported.
- **Milestone 4 — Challenger:** After M3, generate security test cases for findings and patches. Acceptance: tests are reviewable and generation failures are handled.
- **Milestone 5 — Isolated verification:** After M3–4, add a properly isolated execution environment and bounded patch retries. Acceptance: untrusted code never runs on the host, resource limits and retry limits are tested, and results do not assert security solely from passing tests.
- **Milestone 3A - Dataset profiling (in progress):** Full streaming profile completed; preparation remains blocked pending independent checksum and rights verification, split-specific label confirmation and leakage review. Provisional raw-label datasets have now been generated; see Milestone 3B.
- **Milestone 3A.1 - Schema investigation (completed; preparation blocked):** A bounded 100-row-per-split inspection confirmed candidate header differences already handled by the profiler. Local evidence does not verify field equivalence, label meanings or license; obtain the dataset provider's documentation or confirmation before preparation.
- **Milestone 3A.2 - Schema mapping and lightweight validation (completed):** Local headers match the published split schemas; a bounded dry run is available. Full preparation remains blocked by unverified label semantics, local provenance and applicable license.
- **Dataset identity verification (completed with qualification):** Both local CSV MD5 values match user-supplied Zenodo checksums; full class totals corroborate `1` as vulnerable and `0` as non-vulnerable. Zenodo checksums were not independently accessible, and the encoding is inferred from aggregate counts. Provisional raw-label preparation is implemented; training remains blocked pending rights and leakage review.
- **Milestone 3B - Provisional dataset preparation (completed):** Generated deterministic raw-label train, validation and held-out test CSVs; exact hash overlap checks passed. Verified label contract, provenance, rights and project/near-duplicate leakage remain open before training.
- **Milestone 4A - Exploratory ML baseline (implemented):** A 2,000-row Kaggle TF-IDF/logistic baseline ran; the downloaded validation metrics are recorded. Raw-label meaning, rights and leakage remain unresolved.
- **Milestone 4B - Kaggle baseline notebook (implemented):** A small notebook and beginner guide invoke the existing gated baseline on train/validation only. The user ran the baseline on Kaggle and supplied validation metrics; local scikit-learn model tests remain skipped.
- **CodeBERT Kaggle pipeline (exploratory run completed):** A one-epoch Kaggle T4 raw-label run and its locally available metrics are documented in [ML evaluation](docs/ML_EVALUATION.md). The label contract, rights and leakage checks remain pending; the reported checkpoint has not been verified locally.
- **Milestone 5A - React dashboard (implemented):** Local Vite dashboard connects to real scan and consent-gated AI endpoints; production build passes. Browser interaction and a live hosted AI provider have not yet been verified.
- **Milestone 5B - Integration smoke checks (completed; browser pending):** Health, real Bandit Python and ZIP scans, invalid uploads, missing AI configuration and Vite proxy were verified. Build and Python tests pass; browser interaction and live AI remain unverified.
- **Milestone 5C - AI integration review (live verification pending):** Frontend/API contracts, consent, agent handoff and real Bandit scan calls inspected; fake-provider automated tests pass. No provider configuration was available in the checking process, so no live AI request was made. The user reports browser Bandit B307 scanning and real hosted Defender and Challenger responses succeeded.
- **Final demo verification (automated checks completed; rehearsal pending):** Synthetic Python and ZIP fixtures, real Bandit API checks, fake-provider AI workflow tests and a frontend production build support the [demo guide](docs/FINAL_DEMO.md). Current-session browser interaction, responsive visual checks and a live provider request remain unverified; the user previously reported a successful live browser workflow.
- **Source submission:** The [submission checklist](docs/SUBMISSION_CHECKLIST.md) records extraction, dependencies and remaining limitations for the source archive.
- **Milestone 8A - Static patch verification (implemented):** AI review adds a syntax, source-change and existing Bandit-results comparison report. This is not functional testing or isolated execution; manual review remains required. The earlier source submission ZIP predates this milestone.
- **Milestone 8B - Optional bounded refinement (implemented):** With explicit opt-in and hosted-AI consent, a second Defender/Challenger round uses first-round feedback and static verification. Completed first-round results survive second-round failures. Results still require manual review; no code or suggested tests are executed. The source submission ZIP predates this milestone.
- **Milestone 9 - Professional UI redesign (implemented; browser rehearsal pending):** The responsive React workspace presents scan findings, consent-gated AI review, completed rounds and static verification. Automated rendering and request-contract checks supplement the production build; real-browser layout, keyboard interaction and live-provider rehearsal remain pending. The prior submission ZIP has not been rebuilt.
- **Reference-guided UI rebuild (implemented; browser rehearsal pending):** Overview, Scanner, AI Battle and Code Review use the supplied references for their visual language, with a subsequent visual polish pass. The diff is local and bounded, and all scan and review data come from existing API responses. Desktop/mobile visual checks and live-provider rehearsal remain pending; the submission ZIP predates the changes.
- **Code review UX refinement (implemented; browser rehearsal pending):** The bounded line diff tries an exact edit comparison before a flagged approximate fallback, matches CRLF/LF content, and keeps copy text unchanged. Split panes synchronize vertical scrolling; agent details can be expanded on demand. Browser checks remain pending.
- **Hosted AI reliability (implemented; live retest pending):** Strict parsing accepts unambiguous wrapped JSON, transient retries remain bounded, and a validated Defender proposal survives later first-round failures as an explicitly partial result. Mocked transport tests cover the paths; the intermittent live provider failure's exact cause remains unverified.
- **Challenger truncation handling (implemented; live retest pending):** The user observed a provider-reported truncated Challenger response. A compact prompt and one targeted retry, sharing the existing two-attempt limit, retain full review context and preserve partial results if unsuccessful. No live request was made during implementation.
- **Milestone 6 — Dataset preparation:** After M0, verify provenance, license, schema, labels, splits and suitability; prepare reproducible data on E:. Acceptance: documented validation and leakage checks, without modifying the original archive.
- **Milestone 7 — Model experiments:** After M6, evaluate vulnerability classification separately from patch reliability ranking. Acceptance: reproducible training and held-out metrics; train a ranking model only if suitable patch/outcome labels are available, otherwise document the data gap. Vulnerability labels alone do not establish patch reliability.
- **Milestone 8 — Dashboard:** After M1–5, build a React interface for upload, findings, patches and verification results. Acceptance: an end-to-end workflow works with clear errors and limitations.
- **Milestone 9 — Final evaluation:** After M5, M7 and M8, evaluate security, usability and model performance. Acceptance: reproducible results, limitations and project documentation are complete.

**Final submission packaging:** The expanded MVP source archive is rebuilt for submission with static verification, optional refinement, the current dashboard and exploratory metrics. Automated regression and archive checks are reported separately; browser/mobile rehearsal, isolated functional execution and validated model evaluation remain outstanding. No trained patch-reliability ranker is implemented. Git verification for Milestone 0 remains deferred.



- **Review presentation and reconstruction (implemented):** Concise agent results and bounded full-file or full-cell previews use validated scope mappings; second-round failures preserve round one. Larger direct Python sources can use the hash-verified local preview within documented limits; other oversized sources fall back to scoped viewing.

- **Final review UX (implemented):** Scan issue names and independent severity/type percentages, compact consent, per-round ranking links, and full or scoped line diffs are implemented. The frontend suite now covers the current presentation and passes; browser rehearsal remains outstanding.

- **Code Review presentation (implemented):** The ranker hero and proposal cards use actual eligible ranking results and link to the existing full-source or scoped comparison. A browser screenshot attempt failed in the local headless Chrome GPU process; visual browser verification remains outstanding.

- **AI Results and source retention (implemented):** The Results page shares the ranker presentation, while a hash-verified local reconstruction restores larger direct Python previews within browser limits. Notebook and ZIP previews retain the bounded server behavior.

- **Round 2 proposal clarity (implemented):** Optional refinement explicitly requests a distinct targeted alternative when justified; unchanged and duplicate outputs are labeled and excluded from distinct proposal counts and ranking. No additional retries were added.

- **Round 2 truncation handling (implemented):** The Defender refinement sends only the target finding and essential context. A provider length stop preserves Round 1 and logs available token counts to help distinguish routing limits from completion-budget exhaustion.

- **Zero-finding exploration (implemented):** Compact scan coverage and a dedicated exploratory results view distinguish observations from patch reviews and use the returned suggestion list consistently. Coverage is omitted when a measurable denominator is unavailable.

- **Final submission verification (completed):** The source archive includes the demo guide's synthetic input and recorded screenshots. See the [test results](docs/TEST_RESULTS.md) for the final checks and provider verification scope.

- **AI Results and Code Review polish (implemented):** The approved card hierarchy, raw-score ranking, and responsive comparison toolbar are reflected in the React views. Unchanged and duplicate rounds remain inspectable under their round labels.

import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { requestScan, streamReview, hasReviewFile, MISSING_REVIEW_FILE, restoreFullPreview } from './api.js';
import { advanceProgress, ProgressPage, providerError } from './review-progress.jsx';
import { AIResultsPage } from './simple-review.jsx';
import { RankerDemo } from './ranker-demo.jsx';
import { Link, NavigationProvider, useNavigation } from './navigation.jsx';
import { Home, Features, HowItWorks, About, FAQ, Privacy, NotFound } from './public-pages.jsx';
import { ScanResults, ReviewSetup, ReviewResults, CodeReview, PatchOverview } from './workspace-components.jsx';
import { ScanReport, suggestedSelection, findingSelection } from './scan-report.jsx';
import './style.css';

const MAX_UPLOAD = 100 * 1024 * 1024;
const publicLinks = [['/', 'Home'], ['/features', 'Features'], ['/how-it-works', 'How It Works'], ['/about', 'About'], ['/faq', 'FAQs']];
const steps = [['/scan', 'Scan'], ['/results', 'Results'], ['/ai-review', 'AI Review'], ['/code-review', 'Code Review']];
const publicPages = { '/': Home, '/features': Features, '/how-it-works': HowItWorks, '/about': About, '/faq': FAQ, '/privacy': Privacy, '/research/neural-ranking': RankerDemo };

function Header({ initiallyOpen = false }) {
  const { path } = useNavigation();
  const [open, setOpen] = useState(initiallyOpen);
  useEffect(() => setOpen(false), [path]);
  return <header className="site-header"><div className="nav-inner"><Link className="brand" to="/" aria-label="PATCHWARS AI home"><span className="brand-mark"><svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 7v10c0 8-5 13-13 17C8 30 3 25 3 17V7Z"/><path d="m10 17 4 4 8-9"/></svg></span><span>PATCHWARS <b>AI</b></span></Link>
    <button type="button" className="menu-toggle" aria-expanded={open} aria-controls="primary-navigation" aria-label={open ? 'Close navigation menu' : 'Open navigation menu'} onClick={() => setOpen(!open)}>{open ? '×' : '☰'}</button>
    <nav id="primary-navigation" className={`primary-nav ${open ? 'open' : ''}`} aria-label="Main navigation">{publicLinks.map(([url, label]) => <Link key={url} to={url} aria-current={path === url ? 'page' : undefined} onClick={() => setOpen(false)}>{label}</Link>)}<Link to="/scan" className="button primary nav-cta" onClick={() => setOpen(false)}>Start Scanning <span>→</span></Link></nav></div></header>;
}
function Footer() { return <footer className="site-footer"><div className="site-wrap footer-grid"><div><Link className="brand footer-brand" to="/"><span className="brand-mark"><svg viewBox="0 0 32 36" aria-hidden="true"><path d="M16 2 29 7v10c0 8-5 13-13 17C8 30 3 25 3 17V7Z"/><path d="m10 17 4 4 8-9"/></svg></span><span>PATCHWARS <b>AI</b></span></Link><p>A final-year project exploring thoughtful, AI-assisted code security review.</p></div><div><strong>Explore</strong><Link to="/features">Features</Link><Link to="/how-it-works">How It Works</Link><Link to="/about">About</Link></div><div><strong>Resources</strong><Link to="/faq">FAQs</Link><Link to="/privacy">Privacy & limitations</Link><Link to="/research/neural-ranking">Neural Ranker Demo</Link><Link to="/scan">Start scanning</Link></div></div><div className="site-wrap footer-bottom">A research prototype. Findings and generated patches require human review.</div></footer>; }
function StepNav({ path }) { return <nav className="step-nav" aria-label="Analysis steps">{steps.map(([url, name], index) => <React.Fragment key={url}><Link to={url} aria-current={path === url ? 'page' : undefined}><span>{String(index + 1).padStart(2, '0')}</span>{name}</Link>{index < steps.length - 1 && <span className="step-divider" aria-hidden="true">/</span>}</React.Fragment>)}</nav>; }
function Empty({ title, text }) { return <section className="empty-page"><div className="empty-icon">⌘</div><h2>{title}</h2><p>{text}</p><Link className="button primary" to="/scan">Go to Scan →</Link></section>; }
function PageTitle({ eyebrow, title, text }) { return <div className="workspace-title"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{text}</p></div>; }

function ScanProgress({ file, error, retry, chooseAnother, progress }) {
  const upload = progress?.stage === 'upload' && Number.isFinite(progress.loaded) && Number.isFinite(progress.total) && progress.total > 0;
  const analysis = progress?.stage === 'analysis' && Number.isInteger(progress.completed) && Number.isInteger(progress.total) && progress.total > 0 && progress.completed < progress.total;
  const percent = upload ? Math.min(99, Math.max(0, Math.floor(progress.loaded * 100 / progress.total))) : analysis ? Math.floor(progress.completed * 100 / progress.total) : progress?.stage === 'complete' ? 100 : null;
  return <section className="scan-progress" aria-labelledby="scan-progress-title">
    <div className={`scan-progress-card ${error ? 'has-error' : ''}`}>
      <div className="scan-progress-icon" aria-hidden="true"><span className="scan-lens"/></div>
      <span className="report-kicker">STATIC SECURITY SCAN</span>
      <h1 id="scan-progress-title">{error ? 'Scan could not be completed' : progress?.stage === 'complete' ? 'Scan complete' : 'Scanning your code...'}</h1>
      <p className="scan-progress-file">{file?.name}</p>
      {error ? <><p className="scan-progress-error" role="alert">{error}</p><div className="scan-progress-actions"><button className="button primary" type="button" onClick={retry}>Retry scan</button><button className="button secondary" type="button" onClick={chooseAnother}>Choose another file</button></div></> : <>
        <p role="status" aria-live="polite">{progress?.stage === 'upload' ? 'Uploading file' : progress?.stage === 'complete' ? 'Results ready' : progress?.stage === 'analysis' ? (analysis ? 'Analyzing Python code' : 'Completing scan') : 'Validating file and analyzing Python code'}</p>
        {percent !== null && <strong className="scan-upload-percent">{percent}% <small>{upload ? 'uploaded' : 'analyzed'}</small></strong>}
        {(progress?.stage === 'analysis' || progress?.stage === 'complete') && Number.isInteger(progress.total) && <p className="scan-progress-hint">{progress.completed} / {progress.total} scan units analyzed</p>}
        <div className={`scan-indeterminate${percent !== null ? ' is-measured' : ''}`} role="progressbar" aria-label={upload ? 'Upload progress' : 'Scan progress'} aria-valuemin={0} aria-valuemax={100} {...(percent !== null ? { 'aria-valuenow': percent, 'aria-valuetext': `${percent}% ${upload ? 'of upload' : 'of analysis'}` } : {})}><span style={percent !== null ? { width: `${percent}%` } : undefined}/></div>
        {percent === null && progress?.stage !== 'analysis' && <p className="scan-progress-hint">{progress?.stage === 'upload' ? 'Upload progress is unavailable.' : 'Analysis progress is unavailable; results open when the scan finishes.'}</p>}
      </>}
    </div>
  </section>;
}

function ScanPage({ state }) {
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);
  if (state.busy === 'scan' || (state.file && state.error)) return <ScanProgress file={state.file} error={state.error} progress={state.scanProgress} retry={() => state.runScan()} chooseAnother={() => state.clearScan()}/>;
  return <><PageTitle eyebrow="STEP 01 · GET STARTED" title="Let’s look at your code." text="Choose a Python file, notebook or ZIP project to run a static scan."/><div className="scan-layout"><section className="panel upload-panel"><div className="panel-heading"><div><h2>Upload source</h2><p>Files are scanned with Bandit.</p></div><span className="subtle-tag">.PY / .IPYNB / .ZIP</span></div><input ref={input} className="visually-hidden" type="file" accept=".py,.ipynb,.zip" onChange={event => { state.choose(event.target.files?.[0]); event.target.value = ''; }}/>
    <div className={`upload-zone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); if (!state.busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); if (!state.busy) state.choose(event.dataTransfer.files?.[0]); }}><span className="upload-symbol">↑</span><strong>{state.file ? state.file.name : 'Drop your file here'}</strong><p>{state.file ? `${(state.file.size / 1024).toFixed(1)} KiB · ${state.file.name.toLowerCase().endsWith('.zip') ? 'ZIP project' : state.file.name.toLowerCase().endsWith('.ipynb') ? 'Notebook' : 'Python file'} · ${state.error ? 'Scan not completed' : state.busy === 'scan' ? 'Scanning' : 'Ready to scan'}` : 'Python and notebooks up to 100 MiB · ZIP up to 500 MiB'}</p><button type="button" className="button secondary" disabled={!!state.busy} onClick={() => input.current?.click()}>{state.error ? 'Choose another file' : 'Browse files'}</button></div>
    {state.error && <p className="error" role="alert">{state.error}</p>}{state.busy === 'scan' && <p role="status" className="muted">Scanning your source. Larger projects may take a moment.</p>}<p className="muted">Scanning starts automatically after you choose a file.</p></section>
    <aside className="side-note scan-guide"><span className="guide-label">YOUR WORKFLOW</span><h2>From source to insight.</h2><ol className="guide-steps"><li><b>01</b><div><strong>Choose a file</strong><p>Upload Python, a notebook, or a ZIP project.</p></div></li><li><b>02</b><div><strong>Understand the scan</strong><p>See findings and anything that could not be analyzed.</p></div></li><li><b>03</b><div><strong>Explore a finding</strong><p>AI review is optional and requires your consent.</p></div></li></ol><div className="note-rule"/><p>Notebook code cells are scanned separately; unsupported cells are reported. Supported ZIP members are scanned together. Source is never executed.</p><Link className="inline-link" to="/privacy">Privacy and limitations →</Link></aside></div></>;
}
function ResultsPage({ state }) {
  const [exploreSource, setExploreSource] = useState('');
  const [modalConsent, setModalConsent] = useState(false);
  const [modalFinding, setModalFinding] = useState(null);
  const [modalRefine, setModalRefine] = useState(false);
  const dialogRef = useRef(null);
  const triggerRef = useRef(null);
  const reviewing = state.busy === 'review';
  useEffect(() => {
    if (!exploreSource) return;
    const previous = triggerRef.current;
    dialogRef.current?.querySelector('input')?.focus();
    return () => previous?.focus();
  }, [exploreSource]);
  useEffect(() => { if (reviewing) dialogRef.current?.focus(); }, [reviewing]);
  function closeModal() { if (reviewing) return; setExploreSource(''); setModalFinding(null); setModalConsent(false); setModalRefine(false); state.clearReviewError(); }
  function onDialogKeyDown(event) {
    if (event.key === 'Escape' && !reviewing) { event.preventDefault(); closeModal(); }
    if (event.key !== 'Tab') return;
    const items = [...dialogRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), [href]')];
    if (!items.length) { event.preventDefault(); dialogRef.current.focus(); return; }
    const first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  if (!state.scan) return <><PageTitle eyebrow="STEP 02 · SCAN RESULTS" title="Your security scan results" text="Scan a file to understand what was checked."/><Empty title="No scan results yet" text="Upload and scan a Python file, notebook or ZIP project to get started."/></>;
  function review(name, line, rule) {
    if (state.busy) return;
    triggerRef.current = document.activeElement; state.clearReviewError(); setModalConsent(false); setModalRefine(false);
    setModalFinding(line == null ? null : { line, rule }); setExploreSource(name);
  }
  const target = state.scan.review_targets?.[exploreSource];
  return <><ScanReport scan={state.scan} file={state.file} selected={state.selected} selectedLine={state.selectedLine} onReview={review} busy={!!state.busy}/>{exploreSource && <div className="explore-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) closeModal(); }}><section className="explore-modal" role="dialog" aria-modal="true" aria-labelledby="explore-modal-title" aria-describedby="explore-modal-description" tabIndex={-1} ref={dialogRef} onKeyDown={onDialogKeyDown}><h2 id="explore-modal-title">{modalFinding ? 'Review finding with AI' : 'Explore with AI'}</h2><p id="explore-modal-description">{modalFinding ? 'Review a proposed security fix with Defender and Challenger.' : 'Get an AI-powered review of your selected code.'}</p><p className="explore-modal-file">{target?.path || exploreSource}{target?.cell_index != null ? ` · code cell ${target.cell_index + 1}` : ''}{modalFinding ? ` · line ${modalFinding.line} · ${modalFinding.rule}` : ''}</p><label className="explore-consent"><input type="checkbox" checked={modalConsent} disabled={reviewing} onChange={event => setModalConsent(event.target.checked)}/><span>I allow AI to review my selected code.<small>Selected code will be sent to an external AI service.</small></span></label>{modalFinding && <label className="explore-consent"><input type="checkbox" checked={modalRefine} disabled={reviewing} onChange={event => setModalRefine(event.target.checked)}/><span>Try a second fix (optional)<small>Refinement uses additional provider calls.</small></span></label>}{state.reviewError && <p className="explore-modal-error" role="alert">{providerError(state.reviewError.category, state.reviewError.message).message}</p>}{reviewing && <p className="explore-modal-loading" role="status">Reviewing your code...</p>}<div className="explore-modal-actions"><button type="button" className="button secondary" onClick={closeModal} disabled={reviewing}>Cancel</button><button type="button" className="button primary" disabled={!modalConsent || reviewing} onClick={() => modalFinding ? state.runFindingReview(exploreSource, modalFinding, modalConsent, modalRefine) : state.runExploratoryReview(exploreSource, modalConsent)}>{reviewing ? 'Reviewing...' : 'Start AI Review'}</button></div></section></div>}</>;
}
function AIPage({ state }) {
  if (!hasReviewFile(state.file)) return <section className="empty-page" role="alert"><h1>Scan a file first</h1><p>{MISSING_REVIEW_FILE}</p><Link className="button primary" to="/scan">Select a file</Link></section>;
  if (!state.scan) return <><PageTitle eyebrow="STEP 03 · AI REVIEW" title="Review a proposed fix." text="Defender proposes. Challenger examines."/><Empty title="Scan a file first" text="Run a scan and choose a Python file to start an AI review."/></>;
  const currentFindings = state.scan.findings_by_file ? state.scan.findings_by_file[state.selected] : state.scan.findings;
  const totalFindings = state.scan.findings?.length || 0;
  return <><PageTitle eyebrow="STEP 03 · AI REVIEW" title="Review your code with AI" text={currentFindings?.length ? 'AI will suggest a change and check it for possible problems.' : 'Explore the selected code without requesting a patch.'}/><section className="panel review-permission"><ReviewSetup file={state.file} scan={state.scan} selected={state.selected} selectedLine={state.selectedLine} selectedRule={state.selectedRule} totalFindings={totalFindings} busy={state.busy} consent={state.consent} setConsent={state.setConsent} refine={state.refine} setRefine={state.setRefine} runReview={state.runReview} error=""/>{state.busy === 'review' && <p><Link className="inline-link" to="/ai-review/progress">View review progress →</Link></p>}{state.reviewError && state.busy !== 'review' && <p><Link className="inline-link" to="/ai-review/progress">View review error →</Link></p>}{state.review && state.busy !== 'review' && <p><Link className="inline-link" to="/ai-review/results">View previous review →</Link></p>}</section></>;
}
function CodePage({ state }) {
  useEffect(() => {
    if (state.codeTarget) {
      const id = state.codeTarget === 'compare' ? 'code-comparison' : `code-${state.codeTarget}`;
      document.getElementById(id)?.scrollIntoView({ block: 'start' });
      document.getElementById(id)?.focus({ preventScroll: true });
      state.setCodeTarget('');
    }
  }, [state.codeTarget]);
  const showCode = () => {
    const comparison = document.getElementById('code-comparison');
    comparison?.focus({ preventScroll: true });
    comparison?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  };
  const inspect = round => { state.setRound(round); showCode(); };
  return <div className="code-review-page"><PageTitle eyebrow="STEP 04 – CODE REVIEW" title="Compare the patches" text="See which patch the model prefers, compare the code, and review the changes."/>{state.review ? <><PatchOverview review={state.review} onInspect={inspect} onCompare={showCode} backLink={<Link className="button secondary patch-back" to="/ai-review/results">Back to AI Review</Link>}/><section className="panel code-section review-comparison-view" id="code-comparison" aria-labelledby="code-comparison-heading" tabIndex={-1}><h2 id="code-comparison-heading">Original &amp; Proposed Code</h2><CodeReview review={state.review} selectedRound={state.round} setSelectedRound={state.setRound}/></section></> : <section className="empty-page"><h2>No proposal to compare yet</h2><p>Run an AI review to compare code.</p><Link className="button primary" to="/scan">Select original file again</Link></section>}</div>;
}

function Workspace({ path, state }) {
  const Page = { '/scan': ScanPage, '/results': ResultsPage, '/ai-review': AIPage, '/code-review': CodePage }[path];
  const showDashboard = path === '/results' && !!state.scan;
  return <main className={`site-wrap workspace${showDashboard ? ' scan-results-workspace' : ''}`}>{!showDashboard && <StepNav path={path}/>}<Page state={state}/></main>;
}
export async function executeScan(file, guard, callbacks, send = requestScan) {
  if (!file || guard.current) return;
  const controller = new AbortController();
  guard.current = controller;
  callbacks.start();
  try {
    const result = await send('/api/scan/stream', { file, timeout: 150000, signal: controller.signal, onProgress: callbacks.progress });
    // This pause displays a real backend-confirmed 100%; it does not simulate progress.
    if (result.scan_status === 'completed' && typeof document !== 'undefined' && document.visibilityState === 'visible') {
      await new Promise(resolve => {
        const timer = setTimeout(done, 900);
        function done() { clearTimeout(timer); controller.signal.removeEventListener('abort', done); resolve(); }
        controller.signal.addEventListener('abort', done, { once: true });
        if (controller.signal.aborted) done();
      });
    }
    if (controller.signal.aborted) return;
    callbacks.success(result);
  } catch (error) {
    callbacks.failure(error);
  } finally {
    guard.current = null;
    callbacks.finish();
  }
}

function Site() {
  const { path, navigate } = useNavigation();
  const [file, setFile] = useState(null), [scan, setScan] = useState(null), [selected, setSelected] = useState(''), [selectedLine, setSelectedLine] = useState(null);
  const [selectedRule, setSelectedRule] = useState(null);
  const [review, setReview] = useState(null), [consent, setConsent] = useState(false), [refine, setRefine] = useState(false);
  const [busy, setBusy] = useState(''), [error, setError] = useState(''), [reviewError, setReviewError] = useState(''), [round, setRound] = useState(1), [codeTarget, setCodeTarget] = useState('');
  const [progress, setProgress] = useState(null);
  const [scanProgress, setScanProgress] = useState(null);
  const reviewRequest = useRef(null), scanRequest = useRef(null), pathRef = useRef(path);
  pathRef.current = path;
  useEffect(() => () => { reviewRequest.current?.abort(); scanRequest.current?.abort(); }, []);
  function choose(next) {
    if (!next || busy || scanRequest.current) return;
    setFile(null); setScan(null); setSelected(''); setSelectedLine(null); setReview(null); setConsent(false); setRefine(false); setRound(1); setError(''); setReviewError(''); setProgress(null);
    if (!/\.(py|zip|ipynb)$/i.test(next.name) || !next.size) { setError('Choose a nonempty Python, notebook, or ZIP file.'); return; }
    const limit = /\.zip$/i.test(next.name) ? 500 * 1024 * 1024 : MAX_UPLOAD;
    if (next.size > limit) { setError(`This file exceeds the ${limit / 1024 / 1024} MiB limit. Choose another file.`); return; }
    setFile(next); runScan(next);
  }
  function select(name, line = null, rule = null) { if (busy || (name === selected && line === selectedLine && rule === selectedRule)) return; setSelected(name); setSelectedLine(line); setSelectedRule(rule); setReview(null); setConsent(false); setRefine(false); setRound(1); setReviewError(''); setProgress(null); }
  async function runScan(next = file) {
    if (!next || busy || scanRequest.current) return;
    await executeScan(next, scanRequest, {
      start: () => { setBusy('scan'); setScanProgress({stage:'upload'}); setError(''); setReviewError(''); setScan(null); setSelected(''); setSelectedLine(null); setReview(null); setConsent(false); setRefine(false); setRound(1); },
      progress: setScanProgress,
      success: result => { setScan(result); const suggestion = suggestedSelection(result, next); setSelected(suggestion.source); setSelectedLine(suggestion.line); setSelectedRule(result.findings?.[0]?.test_id || null); navigate('/results'); },
      failure: err => setError(err.message),
      finish: () => setBusy(''),
    });
  }
  async function runReview(options = {}) {
    const exploring = options.exploring === true;
    const fromModal = options.fromModal === true;
    const authorized = exploring || fromModal ? options.consent === true : consent;
    const source = exploring || fromModal ? options.source : selected;
    const chosenRefine = exploring ? false : fromModal ? options.refine === true : refine;
    const line = fromModal ? options.finding?.line : selectedLine;
    const rule = fromModal ? options.finding?.rule : selectedRule;
    if (!authorized || busy || reviewRequest.current) return;
    if (!hasReviewFile(file)) { setReviewError({ category: 'missing_file', message: MISSING_REVIEW_FILE }); if (!exploring) navigate('/ai-review/progress'); return; }
    if (!scan || !source || (exploring && ((scan.findings || []).length || suggestedSelection(scan, file).source !== source))) return;
    if (fromModal && !(scan.findings || []).some(item => { const target = findingSelection(scan, file, item); return target?.source === source && target.line === line && target.rule === rule; })) return;
    if (fromModal) { setSelected(source); setSelectedLine(line); setSelectedRule(rule); setConsent(true); setRefine(chosenRefine); setReview(null); setRound(1); }
    const controller = new AbortController();
    reviewRequest.current = controller;
    const timer = setTimeout(() => controller.abort(), chosenRefine ? 550000 : 270000);
    setBusy('review'); setReviewError(''); setProgress(null);
    if (!exploring) { pathRef.current = '/ai-review/progress'; navigate('/ai-review/progress'); }
    try {
      const target = scan.review_targets?.[source];
      const result = await streamReview({ file, member: file.name.toLowerCase().endsWith('.zip') ? (target?.path || source) : undefined, cell: target?.cell_index, findingLine: exploring ? null : line, findingId: exploring ? null : rule, refine: chosenRefine, consent: authorized, signal: controller.signal,
        onEvent: stage => setProgress(current => advanceProgress(current, stage, chosenRefine)) });
      setReview(await restoreFullPreview(file, result)); setRound(1);
      if (result.review_status === 'complete' && result.refinement_status !== 'partial') setProgress({ label: 'Review finalized', percent: 100 });
      if (pathRef.current === (exploring ? '/results' : '/ai-review/progress')) navigate('/ai-review/results');
    } catch (err) {
      setReviewError({ category: err.name === 'AbortError' ? 'timeout_or_interruption' : (err.category || 'connection_error'),
        message: err.name === 'AbortError' ? 'The review timed out or was interrupted. Try again when ready.' : err.message });
    } finally { clearTimeout(timer); reviewRequest.current = null; setBusy(''); }
  }
  function clearScan() { if (!busy) { setFile(null); setError(''); } }
  const state = { file, scan, selected, selectedLine, selectedRule, review, consent, setConsent, refine, setRefine, busy, error, reviewError, progress, scanProgress, round, setRound, codeTarget, setCodeTarget, choose, clearScan, select, runScan, runReview, runFindingReview: (source, finding, authorized, refineReview) => runReview({ fromModal: true, source, finding, consent: authorized, refine: refineReview }), runExploratoryReview: (source, authorized) => runReview({ exploring: true, source, consent: authorized }), clearReviewError: () => setReviewError(''), navigate };
  const PublicPage = publicPages[path];
  const isWorkspace = steps.some(([url]) => path === url);
  const isProgress = path === '/ai-review/progress';
  return <><a className="skip-link" href="#content">Skip to content</a><Header/><div id="content">{isProgress ? <ProgressPage state={state}/> : path === '/ai-review/results' ? <AIResultsPage state={state}/> : isWorkspace ? <Workspace path={path} state={state}/> : PublicPage ? <PublicPage/> : <NotFound/>}</div>{(!isProgress || state.reviewError) && <Footer/>}</>;
}
function App({ initialPath }) { return <NavigationProvider initialPath={initialPath}><Site/></NavigationProvider>; }

export { App, Header, StepNav, ScanPage, ScanProgress, AIPage, ScanResults, ReviewSetup, ReviewResults, CodeReview, publicPages, steps };
if (typeof document !== 'undefined') createRoot(document.getElementById('root')).render(<App/>);

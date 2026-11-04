import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { request } from './api';
import './style.css';

const MAX_UPLOAD = 10 * 1024 * 1024;
const MAX_AI = 32 * 1024;
const bytes = n => n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(2)} MB`;

function Icon({ name, size = 20 }) {
  const paths = {
    shield: <><path d="M12 2 20 5v6c0 5-3 8-8 11-5-3-8-6-8-11V5z"/><path d="m9 12 2 2 4-4"/></>,
    scan: <><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M4 12h16"/></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></>,
    file: <><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 13h6M9 17h6"/></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5"/></>,
    spark: <><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6zM19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z"/></>,
    terminal: <><path d="m5 7 4 4-4 4M12 17h7"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Findings({ findings, empty = 'No findings reported.' }) {
  if (!findings.length) return <div className="clean"><span className="clean-check">✓</span><div><strong>{empty}</strong><small>A clean static scan does not guarantee security.</small></div></div>;
  return <div className="finding-list">{findings.map((f, i) => <article className="finding" key={`${f.test_id}-${f.line_number}-${i}`}>
    <div className="finding-top"><span className={`severity ${String(f.severity).toLowerCase()}`}>{f.severity}</span><span className="finding-id">{f.test_id}</span><span className="finding-line">LINE {f.line_number}</span></div>
    <p>{f.description}</p><div className="finding-meta">CONFIDENCE <b>{f.confidence}</b></div>
  </article>)}</div>;
}

function App() {
  const [connected, setConnected] = useState(null);
  const [file, setFile] = useState(null);
  const [scan, setScan] = useState(null);
  const [review, setReview] = useState(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [tab, setTab] = useState('findings');
  const input = useRef(null);
  useEffect(() => { let active = true; const check = () => request('/health').then(r => { if (active) setConnected(r.status === 'ok'); }).catch(() => { if (active) setConnected(false); }); check(); const id = setInterval(check, 30000); return () => { active = false; clearInterval(id); }; }, []);
  const python = file?.name.toLowerCase().endsWith('.py');
  const groups = scan ? (scan.findings_by_file || { [scan.filename]: scan.findings }) : {};
  const severities = scan ? scan.findings.reduce((a, f) => { const key = String(f.severity).toUpperCase(); a[key] = (a[key] || 0) + 1; return a; }, {}) : {};
  const choose = chosen => {
    setError(''); setScan(null); setReview(null); setConsent(false); setTab('findings');
    if (!chosen) { setFile(null); return; }
    if (!/\.(py|zip)$/i.test(chosen.name)) { setFile(null); setError('Select a .py file or a .zip project.'); return; }
    if (chosen.size > MAX_UPLOAD) { setFile(null); setError('The file exceeds the 10 MiB upload limit.'); return; }
    if (!chosen.size) { setFile(null); setError('Select a file that is not empty.'); return; }
    setFile(chosen);
  };
  async function runScan() {
    if (!file) return; setBusy('scan'); setError(''); setScan(null); setReview(null); setTab('findings');
    try { setScan(await request('/api/scan', { file, timeout: 150000 })); } catch (e) { setError(e.message); } finally { setBusy(''); }
  }
  async function runReview() {
    if (!file || !scan || !python || !consent || file.size > MAX_AI) return;
    setBusy('review'); setError(''); setReview(null);
    try { setReview(await request('/api/ai-review', { file, consent: true, timeout: 270000 })); setTab('defender'); }
    catch (e) { setError(e.message); } finally { setBusy(''); }
  }
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#workspace"><span className="brand-mark"><Icon name="shield" size={22}/></span><span>PATCHWARS <b>AI</b><small>SECURITY WORKSPACE</small></span></a>
      <div className="side-label">WORKSPACE</div><a className="nav-active" href="#workspace"><Icon name="scan" size={18}/> Security review <span>01</span></a><a className="nav-link" href="#results"><Icon name="terminal" size={18}/> Analysis results</a>
      <div className="side-bottom"><div className="side-card"><span className="side-dot"/> PROTOTYPE BUILD<p>Built for careful review, not automated deployment.</p></div><div className="side-footer">PATCHWARS AI <span> / </span> FYP PROJECT</div></div>
    </aside>
    <main id="workspace"><header className="topbar"><div><span className="top-breadcrumb">WORKSPACE</span><span className="breadcrumb-divider">/</span><span>Security review</span></div><div className="top-status"><span className="prototype">PROTOTYPE</span><span className={`status-dot ${connected === true ? 'online' : connected === false ? 'offline' : ''}`}/><span>{connected === null ? 'Checking backend' : connected ? 'Backend connected' : 'Backend offline'}</span></div></header>
      <div className="content"><section className="intro"><div><div className="eyebrow"><span/> SECURITY WORKSPACE <span className="eyebrow-muted"> / 01</span></div><h1>Review code with <em>confidence.</em></h1><p>Scan Python code for security findings, then explore proposed fixes and a second opinion.</p></div><div className="intro-meta"><span>ANALYSIS MODE</span><strong><span className="pulse"/> Static + AI assisted</strong></div></section>
      <div className="workspace-grid"><div className="main-column"><section className="panel upload-panel"><div className="panel-heading"><div><div className="section-index">01 / INPUT</div><h2>Choose your source</h2><p>Start with a Python file or a project archive.</p></div><span className="corner-icon"><Icon name="file"/></span></div>
        <input ref={input} type="file" accept=".py,.zip" hidden onChange={e => { choose(e.target.files?.[0]); e.target.value = ''; }} />
        <button className="dropzone" disabled={!!busy} onClick={() => input.current?.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) choose(e.dataTransfer.files[0]); }}><span className="upload-icon"><Icon name="upload" size={23}/></span><strong>{file ? file.name : 'Select a file or drop it here'}</strong><span>{file ? `${bytes(file.size)} · Ready to scan` : 'Python file or ZIP project · Up to 10 MiB'}</span><span className="browse">{file ? 'CHANGE FILE' : 'BROWSE FILES'} <Icon name="arrow" size={14}/></span></button>
        <div className="upload-footer"><div><span className="privacy-dot"/> Files are sent only when you choose an action.</div><button className="primary" disabled={!file || !!busy} onClick={runScan}>{busy === 'scan' ? 'Scanning...' : 'Run security scan'} <Icon name="arrow" size={17}/></button></div>
      </section>
      {error && <div className="alert error" role="alert"><strong>Unable to complete request</strong><span>{error}</span></div>}
      <section className="panel results-panel" id="results"><div className="panel-heading results-heading"><div><div className="section-index">02 / ANALYSIS</div><h2>Review results</h2><p>Findings and AI feedback appear here.</p></div><span className="panel-chip">{scan ? 'SCAN COMPLETE' : busy === 'scan' ? 'SCANNING' : 'AWAITING INPUT'}</span></div>
        {!scan ? <div className="empty"><div className="empty-icon"><Icon name="scan" size={28}/></div><strong>{busy === 'scan' ? 'Analyzing your source' : 'Your analysis starts here'}</strong><p>{busy === 'scan' ? 'Bandit is scanning your file. Larger projects can take a moment.' : 'Choose a file and run a scan to see its security findings.'}</p></div> : <>
          <div className="tabs" role="tablist"><button role="tab" aria-selected={tab === 'findings'} onClick={() => setTab('findings')}>Findings <span>{scan.total_findings}</span></button><button role="tab" aria-selected={tab === 'defender'} onClick={() => setTab('defender')}>Defender</button><button role="tab" aria-selected={tab === 'challenger'} onClick={() => setTab('challenger')}>Challenger</button></div>
          {tab === 'findings' && <div className="result-body"><div className="summary-row"><div><span>TOTAL FINDINGS</span><strong>{scan.total_findings}</strong></div><div><span>HIGH</span><strong className="red-text">{severities.HIGH || 0}</strong></div><div><span>MEDIUM</span><strong className="amber-text">{severities.MEDIUM || 0}</strong></div><div><span>LOW</span><strong>{severities.LOW || 0}</strong></div></div>{Object.entries(groups).map(([name, findings]) => <div className="file-group" key={name}><div className="file-title"><Icon name="file" size={16}/><strong>{name}</strong><span>{findings.length} {findings.length === 1 ? 'finding' : 'findings'}</span></div><Findings findings={findings}/></div>)}</div>}
          {tab === 'defender' && <div className="result-body">{review ? <><div className="result-lead"><span className="role-symbol defender">✦</span><div><h3>Defender proposal</h3><p>Review the patch manually. It has not been applied.</p></div></div><p className="feedback">{review.defender_explanation}</p><div className="comparison"><div><span>BEFORE</span><strong>{review.bandit_before.length} findings</strong></div><span>→</span><div><span>AFTER</span><strong>{review.bandit_after.length} findings</strong></div></div><p className="disclaimer">A change in findings does not prove security or preserve behavior.</p><details><summary>Original Bandit findings</summary><Findings findings={review.bandit_before}/></details><details><summary>Proposed code Bandit findings</summary><Findings findings={review.bandit_after}/></details><div className="code-grid"><div><div className="code-label">ORIGINAL SOURCE</div><pre><code>{review.original_code}</code></pre></div><div><div className="code-label green-text">PROPOSED PATCH</div><pre><code>{review.proposed_code}</code></pre></div></div></> : <div className="empty compact"><strong>No Defender proposal yet</strong><p>Run an AI review on a Python file to generate a proposal.</p></div>}</div>}
          {tab === 'challenger' && <div className="result-body">{review ? <><div className="result-lead"><span className="role-symbol challenger">✦</span><div><h3>Challenger review</h3><p>A second perspective on the proposed change.</p></div></div><div className="feedback">{review.challenger_feedback}</div><div className="test-heading">SUGGESTED TESTS <span>NOT EXECUTED</span></div>{review.suggested_tests.length ? <ol className="test-list">{review.suggested_tests.map((test,i) => <li key={i}>{test}</li>)}</ol> : <p className="muted">No suggested tests were returned.</p>}<p className="disclaimer">Suggested tests have not been executed. Manual review is required.</p></> : <div className="empty compact"><strong>No Challenger feedback yet</strong><p>Complete an AI review to see suggested checks.</p></div>}</div>}
        </>}</section></div>
      <aside className="right-column"><section className="panel ai-panel"><div className="ai-kicker"><span className="spark-icon"><Icon name="spark" size={18}/></span> AI-ASSISTED REVIEW <span className="beta">BETA</span></div><h2>Two perspectives.<br/><em>One careful review.</em></h2><p>Explore a proposed fix, then let a challenger look for gaps and regressions.</p><div className="role-row"><span className="role-symbol defender">✦</span><div><strong>Defender</strong><small>Proposes a security patch</small></div><span className="role-step">01</span></div><div className="role-row"><span className="role-symbol challenger">✦</span><div><strong>Challenger</strong><small>Reviews and suggests tests</small></div><span className="role-step">02</span></div>
        <div className="consent-box"><strong>Third-party AI provider</strong><p>Your source code and scan findings will be sent to the configured hosted AI provider. The proposed code is also sent for review.</p><label><input type="checkbox" checked={consent} disabled={!!busy || !python} onChange={e => setConsent(e.target.checked)}/><span>I consent to sending this file for AI review.</span></label></div>
        {file && !scan && <p className="limit-note">Run a security scan first to review the file.</p>}{file && !python && <p className="limit-note">AI review supports individual .py files only.</p>}{python && file.size > MAX_AI && <p className="limit-note">AI review is limited to Python files up to 32 KiB.</p>}
        <button className="ai-button" disabled={!file || !scan || !python || file.size > MAX_AI || !consent || !!busy} onClick={runReview}>{busy === 'review' ? 'Reviewing with AI...' : 'Run AI review'} <Icon name="arrow" size={17}/></button><div className="ai-foot">A configured hosted AI provider is required.</div></section>
        <div className="safety-note"><span>!</span><div><strong>Human judgment matters</strong><p>Findings and proposed patches are not security guarantees. Always review before use.</p></div></div><div className="side-signature">PATCHWARS AI <span>©</span> SECURITY RESEARCH</div>
      </aside></div></div></main></div>;
}

createRoot(document.getElementById('root')).render(<App />);

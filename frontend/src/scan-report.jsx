import React, { useRef } from 'react';
import { Link } from './navigation.jsx';

const metricIcons = {
  input: <><path d="M12 3 4 6v6c0 4 3 7 8 9 5-2 8-5 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></>,
  system: <><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m7 9 3 3-3 3m6 0h4"/></>,
  secrets: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3m-4 5v2"/></>,
  coverage: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5m-18 4 9 5 9-5"/></>,
  sparkle: <path d="M12 2.5 13.9 8l5.6 1.9-5.6 1.9-1.9 5.6-1.9-5.6L4.5 9.9 10.1 8 12 2.5ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/>,
  refresh: <><path d="M20 10a8 8 0 0 0-14-4L3 9m0-5v5h5m-4 5a8 8 0 0 0 14 4l3-3m0 5v-5h-5"/></>,
};

function ScanIcon({ name }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{metricIcons[name]}</svg>;
}

function ScanMetric({ label, icon, tone, count, total, unit, detail }) {
  const measured = Number.isInteger(count) && Number.isInteger(total) && total > 0 && count >= 0 && count <= total;
  const percent = measured ? Number((100 * count / total).toFixed(1)) : null;
  return <div className={`scan-metric ${tone}`}>
    <div className="scan-metric-name"><span className="scan-metric-icon"><ScanIcon name={icon}/></span><span>{label}</span></div>
    {measured && <div className={`measured-track ${tone}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${count} of ${total} ${unit}`}><span style={{ '--measured-value': `${100 * count / total}%` }}/></div>}
    <div className="scan-metric-reading"><strong>{measured ? `${percent}%` : 'Not assessed'}</strong>{(detail || measured) && <small>{detail || `${count} of ${total} ${unit}`}</small>}</div>
  </div>;
}

export function findingSelection(scan, file, finding) {
  if (!Number.isInteger(finding.line_number) || finding.line_number < 1) return null;
  const target = Object.entries(scan.review_targets || {}).find(([, item]) => item.path === finding.file_path && (item.cell_index ?? null) === (finding.cell_index ?? null));
  if (target) return { source: target[0], line: finding.line_number, rule: finding.test_id };
  if (!scan.findings_by_file) return { source: file?.name || scan.filename, line: finding.line_number, rule: finding.test_id };
  return null;
}

// Pick one real finding, never invent a source or send an entire archive.
export function suggestedSelection(scan, file) {
  if (scan.scan_status === 'failed') return { source: '', line: null };
  const findings = scan.findings || [];
  if (findings.length) {
    const finding = findings[0];
    const target = Object.entries(scan.review_targets || {}).find(([, item]) => item.path === finding.file_path && (item.cell_index ?? null) === (finding.cell_index ?? null));
    if (target) return { source: target[0], line: finding.line_number };
    if (!scan.findings_by_file) return { source: file.name, line: finding.line_number };
    return { source: '', line: null };
  }
  // Exploration is optional and limited to one small, analyzed source unit.
  if (scan.findings_by_file) {
    const entry = Object.keys(scan.review_targets || {}).find(name => scan.file_sizes?.[name] > 0 && scan.file_sizes[name] <= 6000);
    return { source: entry || '', line: null };
  }
  return { source: file?.size > 0 && file.size <= 6000 ? file.name : '', line: null };
}

// Each rule belongs to at most one risk group; severity is an independent measure.
export const RISK_GROUPS = [
  { key: 'input', title: 'Input & injection', rules: ['B102', 'B307', 'B608', 'B610', 'B611'], tone: 'coral' },
  { key: 'system', title: 'System commands', rules: ['B404', 'B602', 'B603', 'B604', 'B605', 'B606', 'B607', 'B609'], tone: 'amber' },
  { key: 'secrets', title: 'Passwords & crypto', rules: ['B105', 'B106', 'B107', 'B303', 'B304', 'B305', 'B324'], tone: 'cyan' },
];

export function categorizeFindings(findings) {
  const counts = { input: 0, system: 0, secrets: 0, other: 0, high: 0 };
  for (const item of findings) {
    if (String(item.severity || '').toUpperCase() === 'HIGH') counts.high++;
    const group = RISK_GROUPS.find(entry => entry.rules.includes(String(item.test_id || '').toUpperCase()));
    counts[group?.key || 'other']++;
  }
  return counts;
}

export const ISSUE_NAMES = {
  B404: 'Subprocess security warning', B105: 'Hardcoded password', B608: 'Possible SQL injection',
  B602: 'Unsafe shell command', B307: 'Unsafe code execution', B324: 'Weak cryptographic hashing',
  B102: 'Use of exec', B106: 'Hardcoded password argument', B107: 'Hardcoded password default',
  B303: 'Insecure hash function', B304: 'Insecure cipher', B305: 'Insecure cipher mode',
  B603: 'Subprocess call', B604: 'Function call with shell enabled', B605: 'Shell command execution',
  B606: 'Process started without a shell', B607: 'Partial executable path', B609: 'Wildcard command injection',
  B610: 'Possible SQL injection in Django', B611: 'Possible SQL injection in Django',
};
export function issueName(item) { return ISSUE_NAMES[String(item?.test_id || '').toUpperCase()] || 'Security finding'; }

export function IssueRow({ item, scan, file, onReview, busy }) {
  const target = findingSelection(scan, file, item);
  const path = item.file_path || file?.name || scan.filename || 'Unknown file';
  const line = Number.isInteger(item.line_number) && item.line_number > 0 ? `line ${item.line_number}` : 'line not reported';
  const title = issueName(item);
  return <article className="issue-row"><div className="issue-main"><h3>{title}</h3><p>{item.description || 'Bandit did not provide a description.'}</p><div className="issue-location">{path}{item.cell_index != null ? ` - code cell ${item.cell_index + 1}` : ''} - {line}</div></div><div className="issue-meta"><span className={`severity ${String(item.severity || '').toLowerCase()}`}>{item.severity || 'Unknown'} severity</span><details><summary>Technical details</summary><span className="issue-confidence">Bandit rule: {item.test_id || 'not reported'} · Confidence: {item.confidence || 'not reported'}</span></details></div><div className="issue-action">{target ? <button type="button" className="button secondary" disabled={busy} aria-label={`Review ${title} at ${line} with AI`} onClick={() => onReview(target.source, target.line, target.rule)}>Review with AI</button> : <span className="muted">Review unavailable</span>}</div></article>;
}

export function ScanReport({ scan, file, onReview, busy = false }) {
  const findingsPanel = useRef(null);
  const findingsHeading = useRef(null);
  const findings = scan.findings || [];
  const skipped = scan.skipped || [];
  const failed = scan.scan_status === 'failed';
  const partial = scan.scan_status === 'partial';
  const completed = scan.scan_status === 'completed';
  const filename = scan.filename || file?.name;
  const covered = scan.analyzed_source_files;
  const analyzed = failed ? 0 : scan.scan_type === 'notebook' ? (scan.analyzed_cells ?? 0) : covered ?? (completed && !scan.findings_by_file ? 1 : 0);
  const unit = scan.scan_type === 'notebook' ? 'code cell' : 'file';
  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  for (const finding of findings) {
    const severity = String(finding.severity || '').toUpperCase();
    if (Object.hasOwn(counts, severity)) counts[severity]++;
  }
  const categories = categorizeFindings(findings);
  const hasReviewableFinding = !failed && findings.some(finding => findingSelection(scan, file, finding));
  const exploration = !findings.length && analyzed > 0 ? suggestedSelection(scan, file).source : '';

  function startReview() {
    if (!findings.length) {
      onReview(exploration, null);
    } else if (findings.length === 1) {
      const selection = findingSelection(scan, file, findings[0]);
      if (selection) onReview(selection.source, selection.line, selection.rule);
    } else {
      findingsPanel.current.open = true;
      findingsHeading.current.focus();
    }
  }

  return <div className="scan-report">
    <header className="scan-results-heading">
      <h1>Your security scan results</h1>
      <p>{filename}</p>
    </header>

    <section className="scan-results-panel" aria-label="Scan summary">
      <div className="scan-severity-badges" aria-label="Reported severity">
        <span className="scan-severity-label">Findings</span>
        {['High', 'Medium', 'Low'].map(label => <span key={label} className={`severity ${label.toLowerCase()}`}><span>{label}</span><strong>{counts[label.toUpperCase()]}</strong></span>)}
      </div>
      {partial && <p className="scan-results-status" role="status">Partial scan · {skipped.length ? `${skipped.length} skipped ${skipped.length === 1 ? 'item' : 'items'}` : 'Some content could not be analyzed'}</p>}
      {failed && <p className="scan-results-status" role="status">Scan failed</p>}

      <div className="scan-metrics">
        {RISK_GROUPS.map(group => <ScanMetric key={group.key} icon={group.key} label={group.title} tone={group.tone}
          count={categories[group.key]} total={failed ? 0 : findings.length} unit="findings"/>)}
        <ScanMetric icon="coverage" label="Coverage" tone="mint" count={completed ? covered : null}
          total={scan.eligible_source_files} unit="supported files"
          detail={!completed || covered == null ? `${analyzed} ${unit}${analyzed === 1 ? '' : 's'} analyzed` : undefined}/>
      </div>

      {!findings.length && !failed && <p className="scan-results-note">{analyzed
        ? 'No security issues were reported in the code that was analyzed. This does not guarantee the code is secure.'
        : 'No supported code was analyzed.'}</p>}
      {categories.other > 0 && <p className="scan-results-note">{categories.other} {categories.other === 1 ? 'finding uses' : 'findings use'} an unlisted rule.</p>}

      <div className="scan-results-actions">
        <button type="button" className="button primary scan-results-review" disabled={busy || (!hasReviewableFinding && !exploration)} onClick={startReview}>
          <ScanIcon name="sparkle"/>{findings.length || !exploration ? 'Review with AI' : 'Explore this code with AI'}
        </button>
        <Link className="button secondary" to="/scan"><ScanIcon name="refresh"/>Scan another file</Link>
      </div>
    </section>

    <details className="scan-findings" ref={findingsPanel}>
      <summary>View scan findings <span>{findings.length}</span></summary>
      <div className="scan-findings-body">
        {findings.length > 0 ? <>
          <h2 tabIndex={-1} ref={findingsHeading}>Choose a finding to review</h2>
          <p className="muted">AI review sends the selected bounded code region after you give consent.</p>
          <div className="source-card issue-list">{findings.map((item, index) => <IssueRow key={index} item={item} scan={scan} file={file} onReview={onReview} busy={busy || failed}/>)}</div>
        </> : <p className="muted">{analyzed ? 'No findings to display.' : 'No scan findings are available.'}</p>}
        <p className="muted">Runtime errors and code quality · Not assessed</p>
        {skipped.length > 0 && <section className="scan-skipped" aria-label="Skipped items">
          <h2>Skipped items ({skipped.length})</h2>
          <ul>{skipped.map((item, index) => <li key={index}><strong>{item.path}{item.cell_index != null ? ` · code cell ${item.cell_index + 1}` : ''}</strong><span>{item.reason}</span></li>)}</ul>
        </section>}
      </div>
    </details>
  </div>;
}

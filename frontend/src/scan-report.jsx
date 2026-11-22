import React from 'react';
import { Link } from './navigation.jsx';

export function MeasuredBar({ label, value, text, tone = 'cyan' }) {
  if (!Number.isFinite(value) || value < 0 || value > 100) return null;
  return <div className="measured-bar"><div className="measured-bar-label"><span>{label}</span><strong>{text ?? `${value.toFixed(1)}%`}</strong></div><div className={`measured-track ${tone}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(value.toFixed(1))} aria-valuetext={text || `${value.toFixed(1)} percent`}><span style={{ '--measured-value': `${value}%` }}/></div></div>;
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
  { key: 'input', title: 'Input/injection', rules: ['B102', 'B307', 'B608', 'B610', 'B611'], tone: 'amber', description: 'These findings involve input or commands that may be interpreted as code or queries.' },
  { key: 'system', title: 'System commands', rules: ['B404', 'B602', 'B603', 'B604', 'B605', 'B606', 'B607', 'B609'], tone: 'coral', description: 'These findings involve starting processes or using system commands.' },
  { key: 'secrets', title: 'Passwords/cryptography', rules: ['B105', 'B106', 'B107', 'B303', 'B304', 'B305', 'B324'], tone: 'cyan', description: 'These findings involve hardcoded passwords or cryptographic choices.' },
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

function CategoryMeasure({ title, count, total, description, tone }) {
  return <article className="category-measure"><div className="category-measure-head"><h3>{title}</h3><strong>{count} {count === 1 ? 'finding' : 'findings'}</strong></div><p>{description}</p>{total > 0 ? <MeasuredBar label={title} value={100 * count / total} text={`${count} of ${total} findings (${(100 * count / total).toFixed(1)}%)`} tone={tone}/> : null}</article>;
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
  const findings = scan.findings || [];
  const skipped = scan.skipped || [];
  const analyzed = scan.scan_status === 'failed' ? '0 files' : scan.scan_type === 'notebook' ? `${scan.analyzed_cells ?? 0} code ${scan.analyzed_cells === 1 ? 'cell' : 'cells'}` : scan.analyzed_source_files != null ? `${scan.analyzed_source_files} of ${scan.eligible_source_files} supported files` : '1 Python file';
  const analyzedCount = scan.scan_status === 'failed' ? 0 : scan.scan_type === 'notebook' ? (scan.analyzed_cells ?? 0) : scan.analyzed_source_files ?? 1;
  const counts = findings.reduce((result, item) => { const severity = String(item.severity || '').toUpperCase(); result[severity] = (result[severity] || 0) + 1; return result; }, {});
  const categories = categorizeFindings(findings);
  const eligible = scan.eligible_source_files;
  const covered = scan.analyzed_source_files;
  const coverage = scan.scan_status === 'completed' && Number.isInteger(eligible) && eligible > 0 && Number.isInteger(covered) && covered >= 0 && covered <= eligible ? 100 * covered / eligible : null;
  const partial = scan.scan_status !== 'completed';
  const status = scan.scan_status === 'failed' ? 'Scan failed' : partial ? 'Partial scan' : 'Scan complete';
  const selection = suggestedSelection(scan, file);
  const first = findings[0];
  const location = first ? `${first.file_path || file?.name || scan.filename}${first.cell_index != null ? ` · code cell ${first.cell_index + 1}` : ''} · line ${first.line_number}` : selection.source;
  return <div className="scan-report"><header className="report-header"><div><span className="report-kicker">SECURITY SCAN / RESULTS</span><h1>Your security scan results</h1><p>Results for <strong className="file-name">{file?.name || scan.filename}</strong>.</p></div><span className={`report-status ${partial ? 'is-partial' : ''}`}>{status}</span></header>
    <section className="report-overview" aria-label="Scan summary"><div className="overview-intro"><span className="overview-icon" aria-hidden="true">⌁</span><div><span className="report-kicker">WHAT WAS CHECKED</span><strong>{analyzed} analyzed</strong><p>{partial ? 'Some content could not be analyzed.' : 'All supported content in this scan was analyzed.'}</p></div></div><div className="overview-facts"><div><strong>{scan.total_findings}</strong><span>{scan.total_findings === 1 ? 'finding' : 'findings'}</span></div><div><strong>{counts.HIGH || 0} <small>high</small> · {counts.MEDIUM || 0} <small>medium</small> · {counts.LOW || 0} <small>low</small>{findings.length - (counts.HIGH || 0) - (counts.MEDIUM || 0) - (counts.LOW || 0) > 0 && <> · {findings.length - (counts.HIGH || 0) - (counts.MEDIUM || 0) - (counts.LOW || 0)} <small>other</small></>}</strong><span>Reported severity</span></div><div><strong>{skipped.length}</strong><span>Skipped items</span></div></div></section>
    {findings.length > 0 ? <section className="scan-dashboard" aria-label="Security overview"><div className="dashboard-heading"><div><span className="report-kicker">FINDINGS AT A GLANCE</span><h2>Security overview</h2></div><p>Percentages show a share of reported findings, not the chance that code is secure or vulnerable.</p></div><div className="dashboard-grid">
      <h3 className="dashboard-group-title">Security priority</h3>
      {['HIGH', 'MEDIUM', 'LOW'].map(severity => <CategoryMeasure key={severity} title={`${severity[0]}${severity.slice(1).toLowerCase()} severity`} count={counts[severity] || 0} total={findings.length} tone="coral" description="Share of reported findings."/>)}
      <h3 className="dashboard-group-title">Issue types</h3>
      {RISK_GROUPS.map(group => <CategoryMeasure key={group.key} title={group.title} count={categories[group.key]} total={findings.length} tone={group.tone} description={group.description}/>)}
      {categories.other > 0 && <CategoryMeasure title="Other" count={categories.other} total={findings.length} tone="cyan" description="Other reported rules."/>}
      <article className="category-measure"><div className="category-measure-head"><h3>Scan coverage</h3></div>{coverage === null ? <p>Coverage not available for this scan.</p> : <MeasuredBar label="Supported files analyzed" value={coverage} text={Number.isInteger(eligible) && eligible > 0 ? `${covered} of ${eligible} supported files (${coverage.toFixed(1)}%)` : `${coverage.toFixed(1)}% of supported source`}/>}<p>Coverage describes analyzed source, not security.</p></article>
      <article className="category-measure"><div className="category-measure-head"><h3>Runtime errors</h3><strong>Not tested</strong></div><p>Static scanning does not run your code or test its behavior.</p></article>
    </div><p className="dashboard-note">Severity and issue type are separate measures. Each finding appears in one issue type; {categories.other} {categories.other === 1 ? 'finding uses' : 'findings use'} an unlisted rule. See the category mapping in the project README.</p></section> : <section className="scan-dashboard zero-coverage" aria-label="Scan coverage"><h2>Scan coverage</h2>{coverage === null ? <p>Coverage not available for this scan.</p> : <MeasuredBar label="Supported files analyzed" value={coverage} text={`${covered} of ${eligible} supported files (${coverage.toFixed(1)}%)`}/>}<p>Runtime errors: Not tested.</p></section>}
    {partial && <section className="coverage-notice" role="status"><span className="coverage-mark" aria-hidden="true">!</span><div><h2>Some parts could not be analyzed.</h2><p>The results cover only {analyzed}. Skipped content is not considered clean. Notebook magic, shell commands and non-Python cells cannot be analyzed as Python.</p>{skipped.length > 0 && <details><summary>See what was skipped ({skipped.length})</summary><ul>{skipped.map((item, index) => <li key={index}><strong>{item.path}{item.cell_index != null ? ` · code cell ${item.cell_index + 1}` : ''}</strong><span>{item.reason}</span></li>)}</ul></details>}</div></section>}
    {findings.length === 0 ? <section className="zero-notice"><span className="zero-mark" aria-hidden="true">{analyzedCount ? '✓' : '!'}</span><div className="zero-content"><div className="zero-copy"><h2>{analyzedCount ? 'No security issues were reported in the code that was analyzed.' : 'No supported code was analyzed.'}</h2><p>{analyzedCount ? 'This does not guarantee the code is secure.' : 'There is no scan result to assess. Check the skipped items or try another file.'}{partial && analyzedCount ? ' Some content was not analyzed.' : ''}</p>{selection.source && <p>Optional exploration covers one analyzed source unit ({selection.source}); it is not a fix for a detected issue.</p>}<div className="zero-actions"><Link className="button secondary" to="/scan">Scan another file →</Link></div></div>{selection.source && <button type="button" className="button zero-ai-action" disabled={busy} onClick={() => onReview(selection.source, null)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 2.5 13.9 8l5.6 1.9-5.6 1.9-1.9 5.6-1.9-5.6L4.5 9.9 10.1 8 12 2.5ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></svg><span>Explore this code with AI</span></button>}</div></section> : <section className="source-section"><div className="source-heading"><span className="report-kicker">REPORTED ISSUES</span><h2>What the scan found</h2><p>Choose an issue to review. Each finding is a potential issue, not a confirmed vulnerability.</p></div><div className="source-card issue-list">{findings.map((item, index) => <IssueRow key={`${item.file_path || ''}-${item.cell_index ?? ''}-${item.line_number}-${item.test_id}-${index}`} item={item} scan={scan} file={file} onReview={onReview} busy={busy}/>)}</div><p className="muted">AI review sends only the selected bounded code region after you give consent.</p></section>}

  </div>;
}

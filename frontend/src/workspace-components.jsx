import React, { useEffect, useMemo, useState } from 'react';
import { lineDiff, splitDiffRows } from './diff.js';
import { issueName } from './scan-report.jsx';
import './style.css';

const candidateReasons = {
  unchanged_from_original: 'The proposal is unchanged from the original.',
  identical_to_round_one: 'The proposal is identical to Round 1.',
  invalid_or_unchecked_syntax: 'Python syntax is invalid or was not checked.',
  static_scan_unavailable: 'The proposed code could not be scanned.',
  target_rule_still_reported: 'Bandit still reports the targeted rule.',
  possible_unrelated_change: 'Changes outside the targeted statement require review.',
};

// Interpret only the model's returned candidates; never infer a winner from
// incomplete, inconsistent, or duplicate ranking data.
export function reviewRanking(ranking, rounds = [], original) {
  if (ranking?.status === 'single_candidate') return { status: 'single', candidates: [] };
  if (ranking?.status === 'no_valid_candidates' || ranking?.status === 'no_grounded_findings') return { status: 'none', candidates: [] };
  if (ranking?.status !== 'available' || !Array.isArray(ranking.candidates) || ranking.candidates.length < 2) return { status: 'unavailable', candidates: [] };
  const candidates = ranking.candidates;
  const rankedRounds = candidates.map(candidate => rounds.find(round => round.round === candidate.round));
  const codes = rankedRounds.map(round => round?.proposed_code);
  if (candidates.some(candidate => !Number.isFinite(candidate.score) || !Number.isInteger(candidate.rank) || candidate.rank < 1 ||
      rounds.find(round => round.round === candidate.round)?.candidate_assessment?.ranking_eligible === false) ||
      codes.some(code => typeof code !== 'string' || !code.trim()) || new Set(codes).size !== codes.length ||
      (typeof original === 'string' && rankedRounds.some(round => proposalStatus(round, original, rounds) !== 'changed')) ||
      new Set(candidates.map(candidate => candidate.round)).size !== candidates.length) return { status: 'unavailable', candidates: [] };
  const top = Math.max(...candidates.map(candidate => candidate.score));
  const winners = candidates.filter(candidate => candidate.score === top);
  if (candidates.some(candidate => (candidate.rank === 1) !== (candidate.score === top))) return { status: 'unavailable', candidates: [] };
  const low = Math.min(...candidates.map(candidate => candidate.score));
  const range = top - low;
  return { status: winners.length === 1 ? 'preferred' : 'tie', winner: winners.length === 1 ? winners[0].round : null,
    candidates: candidates.map(candidate => ({ ...candidate, position: range === 0 || !Number.isFinite(range) ? null : (candidate.score - low) / range })) };
}

function CandidateEligibility({ rounds, showUnassessed = false }) {
  const rejected = rounds.filter(round => round.candidate_assessment?.reasons?.length || (showUnassessed && !round.candidate_assessment));
  return rejected.length > 0 && <ul>{rejected.map(round => <li key={round.round}>Round {round.round}: {round.candidate_assessment ? round.candidate_assessment.reasons.map(reason => candidateReasons[reason] || 'Candidate did not meet a ranking check.').join(' ') : 'Eligibility was not recorded for this proposal.'}</li>)}</ul>;
}

function Findings({ items = [], onSelectFinding, selectedLine }) {
  if (!items.length) return <p className="muted">No Bandit findings reported.</p>;
  return <ul className="findings">{items.map((item, index) => <li key={`${item.test_id}-${item.line_number}-${index}`}><span className={`severity ${String(item.severity || '').toLowerCase()}`}>{item.severity || 'Unknown'}</span><strong>{item.test_id}</strong><span className="muted">Line {item.line_number}</span><p>{item.description}</p>{onSelectFinding && <button type="button" className="text-button" aria-pressed={selectedLine === item.line_number} onClick={() => onSelectFinding(item.line_number)}>{selectedLine === item.line_number ? 'Finding selected' : 'Review this finding'}</button>}</li>)}</ul>;
}

function ScanResults({ scan, selected, selectedLine, onSelect = () => {}, onSelectFinding, busy = false }) {
  if (!scan) return <p className="muted">Your findings will appear here after the scan.</p>;
  const groups = scan.findings_by_file || { [scan.filename]: scan.findings };
  return <><div className="summary-row"><strong>{scan.total_findings} {scan.total_findings === 1 ? 'finding' : 'findings'}</strong><span>Static analysis is not a security guarantee.</span></div>
    {scan.findings_by_file && <p className="muted">Choose one Python file for AI review.</p>}
    <div className="file-list">{Object.entries(groups).map(([name, findings]) => {
      const size = scan.file_sizes?.[name];
      const eligible = size === undefined || size > 0;
      return <article className={`file-item ${selected === name ? 'selected' : ''}`} key={name}>
        <div className="file-heading"><div><strong className="file-name">{name}</strong><span className="muted">{findings.length} {findings.length === 1 ? 'finding' : 'findings'}{!eligible ? ' · AI review requires nonempty source up to 32 KiB' : ''}</span></div>{scan.findings_by_file && <button type="button" className="button secondary" aria-pressed={selected === name} disabled={!eligible || busy} onClick={() => onSelect(name)}>{selected === name ? 'Selected' : 'Select file'}</button>}</div>
        <details><summary>View findings</summary><Findings items={findings} selectedLine={selected === name ? selectedLine : null} onSelectFinding={!busy && onSelectFinding ? line => onSelectFinding(name, line) : undefined}/></details>
      </article>;
    })}</div></>;
}

function ReviewSetup({ file, scan, selected, selectedLine, selectedRule, busy, consent, setConsent, refine, setRefine, runReview, error }) {
  const target = scan?.review_targets?.[selected];
  const path = target?.path || selected || (file?.name?.toLowerCase().endsWith('.zip') ? '' : file?.name);
  const selectedFindings = scan?.findings_by_file ? scan.findings_by_file[selected] : scan?.findings;
  const finding = selectedFindings?.find(item => item.line_number === selectedLine && (!selectedRule || item.test_id === selectedRule));
  const hasFindings = !!selectedFindings?.length;
  const size = scan?.file_sizes?.[selected] ?? file?.size;
  const ready = !!scan && !!path && (size <= 6000 || selectedLine != null);
  return <div className="compact-review"><h2>Selected issue</h2><p><strong>{finding ? issueName(finding) : hasFindings ? 'Security finding' : 'Exploratory code review'}</strong><br/>{path || 'No source selected'}{target?.cell_index != null ? ` - code cell ${target.cell_index + 1}` : ''}{selectedLine != null ? ` - line ${selectedLine}` : ''}</p><p>{finding?.description || (hasFindings ? 'Select an issue to review.' : 'No issue was reported; AI can provide an exploratory review.')}</p>
    {!ready && <p className="warning">Select an eligible issue from Scan Results first.</p>}
    <h2>What AI does</h2>{hasFindings ? <ol><li>Defender suggests a change.</li><li>Challenger checks the suggestion.</li></ol> : <p>AI provides an explanation; no patch is requested.</p>}
    <div className="options"><label><input type="checkbox" checked={consent} disabled={!ready || !!busy} onChange={e => setConsent(e.target.checked)}/><span>Allow AI to review my selected code<small>Your selected code is sent to an external AI service. Your original file stays unchanged.</small></span></label>
    {hasFindings && <label><input type="checkbox" checked={refine} disabled={!ready || !!busy} onChange={e => setRefine(e.target.checked)}/><span>Try a second fix (optional)<small>AI can try another version after feedback. This uses additional API calls.</small></span></label>}</div>
    <button className="button primary" type="button" disabled={!ready || !consent || !!busy} onClick={runReview}>{busy === 'review' ? 'Reviewing...' : 'Start AI Review'}</button>
    {busy === 'review' && <p role="status">Review in progress.</p>}{error && <p className="error" role="alert">{error}</p>}</div>;
}

function Rounds({ rounds, selectedRound, setSelectedRound }) {
  return <div role="group" aria-label="Review round">{rounds.map(item => <button key={item.round} type="button" className="button secondary" aria-pressed={item.round === selectedRound} onClick={() => setSelectedRound(item.round)}>Round {item.round}</button>)}</div>;
}

function ReviewResults({ review, selectedRound, setSelectedRound, openCode }) {
  const rounds = review?.rounds || [];
  const round = rounds.find(item => item.round === selectedRound) || rounds[0];
  const summary = text => text ? (text.length > 180 ? `${text.slice(0, 180).trimEnd()}…` : text) : 'Not available.';
  return <><div className="workflow" aria-label="Review workflow"><span>Scan</span><span>Defender</span><span>Challenger</span><span>Verify</span></div>
    {!round ? <p className="muted">Your review will appear here.</p> : <>
      {(review.review_status === 'partial' || review.refinement_status === 'partial') && <p className="warning" role="status">Review incomplete. {review.review_failure?.message || review.refinement_error} The available proposal is preserved.</p>}
      <Rounds rounds={rounds} selectedRound={selectedRound} setSelectedRound={setSelectedRound}/>
      <div className="agent-grid"><article className="agent"><span className="agent-label">DEFENDER</span><h3>Patch proposal</h3><p>{summary(round.defender_explanation)}</p><span className="tag">Not applied</span><details><summary>Full explanation</summary><p>{round.defender_explanation}</p></details><button type="button" className="text-button" onClick={openCode}>View proposed code →</button></article>
      <article className="agent challenger"><span className="agent-label">CHALLENGER</span><h3>Review & concerns</h3><p>{summary(round.challenger_feedback)}</p><span className="tag">{Array.isArray(round.suggested_tests) ? `${round.suggested_tests.length} suggested tests · not executed` : 'Tests unavailable'}</span><details><summary>Full review and tests</summary><p>{round.challenger_feedback || 'Challenger review did not complete.'}</p>{round.suggested_tests?.length > 0 && <ul>{round.suggested_tests.map((test, index) => <li key={index}>{test}</li>)}</ul>}</details></article></div>
    </>}</>;
}

function HighlightedCode({ text }) {
  const tokens = String(text || '').split(/(#[^\n]*|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\b(?:def|class|return|import|from|as|if|else|elif|for|while|try|except|with|raise|pass|True|False|None|async|await)\b)/g);
  return <>{tokens.map((token, index) => <span key={index} className={token.startsWith('#') ? 'syntax-comment' : /^["']/.test(token) ? 'syntax-string' : /^(def|class|return|import|from|as|if|else|elif|for|while|try|except|with|raise|pass|True|False|None|async|await)$/.test(token) ? 'syntax-keyword' : undefined}>{token}</span>)}</>;
}

export async function copySource(value, clipboard) {
  await clipboard.writeText(value);
}

export function staticOutcome(before, after, verification) {
  if (verification?.target_rule_still_reported === true) return 'The targeted rule is still reported.';
  if (!Array.isArray(before) || !Array.isArray(after)) return 'Static comparison unavailable.';
  if (verification?.target_rule_still_reported === false && verification?.introduced_findings?.length > 0 && after.length >= before.length)
    return 'The original reported issue is no longer detected, but another issue appeared. Overall findings did not decrease.';
  if (verification?.target_rule_still_reported === false) return 'The targeted rule was not reported in the proposed scope.';
  return 'The targeted issue status was not checked.';
}

export function proposalStatus(round, original, rounds) {
  if (typeof original !== 'string' || typeof round?.proposed_code !== 'string') return 'unavailable';
  if (round.proposed_code === original) return 'unchanged';
  if (rounds.some(other => other.round < round.round && other.proposed_code === round.proposed_code)) return 'duplicate';
  return 'changed';
}

export function reviewPoints(value) {
  if (typeof value !== 'string') return [];
  const sentences = value.split(/\n+/).flatMap(line => line.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, '').trim().split(/(?<=[.!?;])\s+/));
  return [...new Set(sentences.filter(Boolean))].slice(0, 3).map(sentence => {
    if (sentence.length <= 150) return sentence;
    const excerpt = sentence.slice(0, 150);
    const end = excerpt.lastIndexOf(' ');
    return `${end > 0 ? excerpt.slice(0, end) : excerpt}…`;
  });
}

export function PatchOverview({ review, onInspect, onCompare, backLink }) {
  const rounds = (review?.rounds || []).filter(round => typeof round.proposed_code === 'string' && round.proposed_code.trim());
  const ranking = reviewRanking(review?.neural_ranking, rounds, review.original_code);
  const changedCount = typeof review.original_code === 'string' ? rounds.filter(round => proposalStatus(round, review.original_code, rounds) === 'changed').length : null;
  const eligibleCount = ranking.status === 'single' ? 1 : ranking.status === 'none' ? 0 :
    ['preferred', 'tie'].includes(ranking.status) ? ranking.candidates.length : null;
  const title = ranking.status === 'preferred' ? <>Recommended patch: <span>Patch {ranking.winner}</span></> :
    ranking.status === 'tie' ? 'Both patches received the same score.' :
    ranking.status === 'single' ? 'Only one eligible patch is available. A comparison is unavailable.' :
    ranking.status === 'none' ? 'No eligible fixes were generated.' : 'Neural ranking is unavailable.';
  return <div className="patch-overview">
    <p className="patch-notice"><span aria-hidden="true">!</span><strong>Patch not applied yet. Review before using.</strong></p>
    <section className="ranker-hero" aria-labelledby="ranker-hero-title"><div className="ranker-hero-heading"><span className="ranker-icon" aria-hidden="true"><svg viewBox="0 0 40 40" fill="none"><path d="M20 7c-3-4-9-1-9 3-5 0-7 6-4 9-3 4 0 9 4 9 0 5 6 7 9 3m0-24c3-4 9-1 9 3 5 0 7 6 4 9 3 4 0 9-4 9 0 5-6 7-9 3m0-24v24M11 15c3 0 5 2 5 4m-5 7c0-3 2-5 5-5m13-6c-3 0-5 2-5 4m5 7c0-3-2-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg></span><h2 id="ranker-hero-title">Neural Patch Ranker</h2></div>
      <div className="ranker-hero-body"><div><h3>{title}</h3><p>{ranking.status === 'preferred' ? 'The experimental model ranked this patch above the other available options.' : ranking.status === 'tie' ? 'The model reports no unique preference.' : 'The model can compare distinct eligible patches when ranking results are available.'}</p></div>
      {ranking.candidates.length > 0 && <div className="ranker-scores" aria-label="Model preference scores">
        {[...ranking.candidates].sort((a, b) => a.round - b.round).map(candidate => <div className={`ranker-score${ranking.winner === candidate.round ? ' is-preferred' : ''}`} key={candidate.round}>
          <strong>Patch {candidate.round}</strong><div className="ranker-score-track" aria-hidden="true"><span style={{width: candidate.position == null ? '50%' : `${candidate.position * 100}%`}}/></div><span className="ranker-score-value">Score {candidate.score}</span>
        </div>)}
        <p>Raw model scores. Bars show relative positions.</p>
      </div>}</div>
    </section>
    {rounds.length > 0 && <section className="patch-cards" aria-label="Patch proposals">{rounds.map(round => {
      const preferred = ranking.winner === round.round;
      const status = proposalStatus(round, review.original_code, rounds);
      const hasProposal = status !== 'unchanged' && status !== 'duplicate';
      const label = `${hasProposal ? 'Patch' : 'Round'} ${round.round}`;
      const summary = { unchanged: 'Unchanged · No new patch generated.', duplicate: 'Duplicate proposal.', changed: 'Code change proposed.', unavailable: 'Change status unavailable.' }[status];
      const points = hasProposal ? reviewPoints(round.defender_explanation) : [];
      if (hasProposal && points.length < 3 && round.verification?.target_rule_still_reported != null) {
        points.push(staticOutcome(review.bandit_before, round.bandit_after, round.verification));
      }
      return <article key={round.round} className={`patch-card${preferred ? ' is-preferred' : ''}`}>
        <div className="patch-card-heading"><span className="patch-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="m12 2 10 6-10 6L2 8l10-6Zm10 10-10 6-10-6m20 4-10 6-10-6"/></svg></span><h3>{label}</h3>{preferred && <span className="patch-preferred">✓ Recommended</span>}</div>
        {points.length > 0 ? <ul>{points.map(point => <li key={point}>{point}</li>)}</ul> : <p className="patch-round">{summary}</p>}
        <button type="button" className="patch-card-button" onClick={() => onInspect(round.round)}>View {label} code</button>
      </article>;
    })}</section>}
    {review.refinement_status === 'partial' && <p className="patch-partial" role="status">The second review did not complete. Available proposals are shown.</p>}
    <div className="patch-actions"><button type="button" className="button primary patch-primary" onClick={onCompare} disabled={!rounds.length}>View Original &amp; Proposed Code</button>{backLink}</div>
    <p className="patch-safety">Review and test before using. The patch has not been applied.</p>
    <details className="patch-technical"><summary>Technical details</summary><p>Model status: {review.neural_ranking?.status || 'unavailable'}.</p><p>Review rounds completed: {rounds.filter(round => round.round_status !== 'partial').length} · Distinct changed proposals: {changedCount ?? 'Unavailable'} · Distinct eligible patches: {eligibleCount ?? 'Unavailable'}</p><p>Static analysis and model preference do not establish security or functional correctness. Tests were not executed.</p>{review.refinement_error && <p>{review.refinement_error}</p>}<CandidateEligibility rounds={rounds}/></details>
  </div>;
}

function CodeReview({ review, selectedRound, setSelectedRound }) {
  const [copyStatus, setCopyStatus] = useState('');
  const [visible, setVisible] = useState(800);
  const [mode, setMode] = useState('split');
  const [sourceView, setSourceView] = useState('full');
  const rounds = review?.rounds || [];
  const round = rounds.find(item => item.round === selectedRound) || rounds[0];
  const fullOriginal = review?.full_original_code ?? (review?.scope?.kind === 'file' ? review.original_code : null);
  const fullProposed = round?.full_proposed_code ?? (review?.scope?.kind === 'file' ? round?.proposed_code : null);
  const hasFullSource = typeof fullOriginal === 'string' && typeof fullProposed === 'string';
  const full = hasFullSource && sourceView === 'full';
  const original = full ? fullOriginal : review?.original_code || '';
  const proposed = full ? fullProposed : round?.proposed_code || '';
  const diff = useMemo(() => lineDiff(original, proposed), [original, proposed]);
  const rows = useMemo(() => splitDiffRows(diff.operations), [diff]);
  useEffect(() => { setVisible(800); setCopyStatus(''); }, [review, selectedRound, sourceView]);
  if (!round) return <p className="muted">Run an AI review to compare a proposed patch.</p>;
  async function copy(value, label) { try { await copySource(value, navigator.clipboard); setCopyStatus(`${label} copied.`); } catch { setCopyStatus('Copy failed. Select the code manually.'); } }
  const renderLine = (item, side, index) => <div key={index} className={`code-line ${item?.type || 'blank'}`}><span>{item ? (side === 'old' ? item.oldLine : item.newLine) : ''}</span><b className="line-sign" aria-hidden="true">{item?.type === 'add' ? '+' : item?.type === 'remove' ? '-' : ' '}</b><code><HighlightedCode text={item?.text || ' '}/></code></div>;
  const verification = round.verification;
  const removed = diff.operations.filter(item => item.type === 'remove').length;
  const added = diff.operations.filter(item => item.type === 'add').length;
  return <><p className="warning">Patch not applied - Tests not executed - Manual review required</p>
    <div className="review-heading"><strong className="file-name">{review.selected_file || review.filename}</strong>{review.scope?.cell_index != null && <span> - notebook code cell {review.scope.cell_index + 1}</span>}</div>
    <div className="review-diff-toolbar">
      <div className="diff-control-group" role="group" aria-label="Patch selection">{rounds.map(item => <button key={item.round} type="button" className="button secondary" aria-pressed={round.round === item.round} onClick={() => setSelectedRound(item.round)}>Round {item.round}</button>)}</div>
      <div className="diff-control-group" role="group" aria-label="Code scope"><button type="button" className="button secondary" aria-pressed={!full} onClick={() => setSourceView('scoped')}>Scoped Diff</button>{hasFullSource && <button type="button" className="button secondary" aria-pressed={full} onClick={() => setSourceView('full')}>Full Source View</button>}</div>
      <div className="diff-controls">
        <div className="diff-control-group" role="group" aria-label="Copy code"><button type="button" className="button secondary" onClick={() => copy(original, 'Original')}>Copy Original</button><button type="button" className="button secondary" onClick={() => copy(proposed, 'Proposed code')}>Copy Proposed Code</button></div>
        <div className="diff-control-group" role="group" aria-label="Diff view"><button type="button" className="button secondary" aria-pressed={mode === 'split'} onClick={() => setMode('split')}>Split</button><button type="button" className="button secondary" aria-pressed={mode === 'unified'} onClick={() => setMode('unified')}>Unified</button></div>
      </div>
    </div>
    <p className="muted">{full ? (review.scope?.cell_index != null ? 'Complete selected code cell; not the whole notebook.' : 'Complete selected Python file.') : 'Reviewed code section only.'} {diff.coarse ? 'Large comparison uses an approximation. ' : ''}Red lines are removed; green lines are added.</p>
    {!hasFullSource && <p className="muted">Full source preview is unavailable. <a href="/scan">Select original file again</a> to start a new review.</p>}
    {mode === 'split' ? <div className="diff-grid"><section className="code-panel"><div className="code-head"><strong>Original code</strong></div><div className="code-scroll" tabIndex={0} role="region" id="code-original" aria-label="Original code">{rows.slice(0, visible).map((row, index) => renderLine(row.left, 'old', index))}</div></section><section className="code-panel"><div className="code-head"><strong>Proposed code - Not applied</strong></div><div className="code-scroll" tabIndex={0} role="region" id="code-proposed" aria-label="Proposed code">{rows.slice(0, visible).map((row, index) => renderLine(row.right, 'new', index))}</div></section></div> : <section className="code-panel"><div className="code-head"><strong>Unified comparison - Proposed code not applied</strong></div><div className="code-scroll" tabIndex={0} role="region" aria-label="Unified code diff">{diff.operations.slice(0, visible).map((item, index) => renderLine(item, item.type === 'remove' ? 'old' : 'new', index))}</div></section>}
    {visible < (mode === 'split' ? rows.length : diff.operations.length) && <button type="button" className="text-button" onClick={() => setVisible(count => count + 800)}>Show more lines</button>}<p className="muted" aria-live="polite">{copyStatus}</p>
    <section className="comparison"><h3>Changes suggested</h3><ul><li>{removed} {removed === 1 ? 'line' : 'lines'} removed, {added} {added === 1 ? 'line' : 'lines'} added{diff.coarse ? ' (approximate)' : ''}.</li><li>Targeted issue: {issueName(review.target_finding || review.bandit_before?.[0])}.</li><li>{staticOutcome(review.bandit_before, round.bandit_after, verification)}</li><li>Remaining findings: {verification?.remaining_findings?.length ?? 'Unavailable'}; introduced findings: {verification?.introduced_findings?.length ?? 'Unavailable'}.</li><li>Challenger: {round.challenger_feedback?.split(/(?<=[.!?])\s/)[0] || 'Not available.'}</li></ul><CandidateEligibility rounds={[round]}/>
    <details><summary>Static finding details</summary>{[['Original', review.bandit_before], ['Proposed', round.bandit_after], ['Remaining', verification?.remaining_findings], ['Introduced', verification?.introduced_findings]].map(([label, findings]) => <section key={label}><h4>{label}</h4>{Array.isArray(findings) ? <Findings items={findings}/> : <p>Unavailable.</p>}</section>)}</details></section></>;
}


export { ScanResults, ReviewSetup, ReviewResults, CodeReview, CandidateEligibility };

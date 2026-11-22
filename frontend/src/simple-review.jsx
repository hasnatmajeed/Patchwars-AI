import React from 'react';
import { Link } from './navigation.jsx';
import { providerError } from './review-progress.jsx';
import { CandidateEligibility, staticOutcome, proposalStatus, reviewRanking, reviewPoints } from './workspace-components.jsx';
import { lineDiff } from './diff.js';
import { issueName } from './scan-report.jsx';

const short = value => typeof value === 'string' && value.trim() ? value.trim().split(/(?<=[.!?])\s/)[0].slice(0, 180) : 'Not available.';

function ExploratoryResults({ review }) {
  const feedback = typeof review.exploratory_feedback === 'string' ? review.exploratory_feedback.trim() : '';
  const sentences = feedback ? feedback.split(/(?<=[.!?])\s+/) : [];
  const tests = Array.isArray(review.suggested_tests) ? review.suggested_tests : null;
  return <main className="site-wrap workspace simple-review exploratory-results">
    <header className="simple-review-header"><h1>Your code analysis</h1><p>Exploratory analysis {review.review_status === 'complete' ? 'complete' : 'incomplete'} · {review.selected_file || review.filename}{review.scope?.cell_index != null ? ` · notebook code cell ${review.scope.cell_index + 1}` : ''}</p></header>
    <section className="simple-agents" aria-label="Exploratory analysis"><article className="simple-agent"><h2>What the AI noticed</h2><ul>{sentences.length ? sentences.slice(0, 2).map((sentence, index) => <li key={index}>{short(sentence)}</li>) : <li>No observations available.</li>}</ul></article><article className="simple-agent challenger"><h2>Possible concerns</h2><ul><li>The response did not identify concerns separately; review the full observations below.</li><li>AI observations are not confirmed security findings.</li></ul></article></section>
    <section className="simple-agent exploratory-checks"><h2>Suggested checks</h2>{tests === null ? <p>Suggestions are unavailable.</p> : tests.length ? <><p>{tests.length} suggested {tests.length === 1 ? 'check' : 'checks'} · not executed</p><ul>{tests.map((test, index) => <li key={index}>{test}</li>)}</ul></> : <p>No checks were suggested.</p>}</section>
    <section className="simple-agent exploratory-next"><h2>What you can do next</h2><ul><li>Review the observations and run relevant checks yourself.</li><li><Link to="/results">Return to scan results</Link> to review analyzed or skipped content.</li></ul></section>
    <p className="exploratory-ranker-note">No patch was requested. Neural ranking is available when there are valid patch proposals to compare. <Link to="/research/neural-ranking">View the Neural Ranking Research Demo</Link>.</p>
    <details className="simple-technical"><summary>Technical details</summary><div className="technical-content"><p>Scope: {review.scope?.kind || 'unavailable'}{review.scope?.cell_index != null ? `, notebook cell ${review.scope.cell_index + 1}` : ''}.</p><p>Full AI observations: {feedback || 'Not available.'}</p><p>Suggested checks: {tests === null ? 'Unavailable.' : tests.length ? tests.join('; ') : 'None suggested.'}</p><p>Tests were not executed.</p></div></details>
  </main>;
}

export function NeuralRanking({ ranking, rounds = [], setRound = () => {} }) {
  const candidates = (ranking?.candidates || []).filter(c => rounds.some(r => r.round === c.round));
  const winners = candidates.filter(c => c.rank === 1);
  const distinct = new Set(candidates.map(c => rounds.find(r => r.round === c.round)?.proposed_code)).size === candidates.length;
  let message = 'Neural ranking unavailable.';
  if (ranking?.status === 'no_valid_candidates' || ranking?.status === 'no_grounded_findings') message = 'No valid patches available for ranking.';
  else if (ranking?.status === 'single_candidate' || ranking?.reason === 'identical_candidates') message = '1 valid patch available. No comparison yet.';
  else if (ranking?.status === 'available' && candidates.length >= 2 && !distinct) message = 'Identical code cannot be compared as distinct patches.';
  else if (ranking?.status === 'available' && candidates.length >= 2) message = winners.length === 1 ? `Model prefers Patch ${winners[0].round} (Round ${winners[0].round})` : 'The model reports a tie; no unique preference.';
  return <section className="neural-ranking"><h2>Neural Patch Ranker</h2><p><strong>{message}</strong></p>{ranking?.status === 'available' && candidates.length >= 2 && distinct && <ul>{candidates.map(candidate => <li key={candidate.round}>Rank {candidate.rank}: Patch {candidate.round}, Round {candidate.round}</li>)}</ul>}{rounds.map(item => <div key={item.round}><p>Patch {item.round} · Round {item.round}{item.candidate_assessment?.ranking_eligible === false ? ' · Excluded from ranking' : ''}</p><Link className="button secondary" to="/code-review" onClick={() => setRound(item.round)}>View Patch {item.round} code</Link></div>)}<CandidateEligibility rounds={rounds}/></section>;
}


function ResultIcon({ name }) {
  const paths = {
    defender: <path d="M12 2 21 5.5v6.2c0 5-3.4 8.3-9 10.3-5.6-2-9-5.3-9-10.3V5.5L12 2Z"/>,
    challenger: <path d="m13 2-9 12h7l-1 8 10-12h-7l.5-8Z"/>,
    award: <><circle cx="12" cy="9" r="6"/><path d="m8 14-1 8 5-3 5 3-1-8M10 9l1.4 1.4L14.5 7"/></>,
    code: <><path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></>,
  };
  return <span className="result-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg></span>;
}

function ActionIcon({ target }) {
  return <svg className="result-action-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{target === 'original' ? <><path d="M6 2h8l4 4v16H6zM14 2v5h5M9 12h6M9 16h6"/></> : target === 'proposed' ? <><circle cx="6" cy="5" r="2"/><circle cx="18" cy="7" r="2"/><circle cx="6" cy="19" r="2"/><path d="M6 7v10M18 9c0 5-12 3-12 8"/></> : <><path d="M3 8h17m-4-4 4 4-4 4M21 16H4m4-4-4 4 4 4"/></>}</svg>;
}

export function AIResultsPage({ state }) {
  const review = state.review;
  if (!review) {
    const guidance = state.reviewError && providerError(state.reviewError.category, state.reviewError.message);
    if (guidance) return <main className="site-wrap workspace result-page"><header className="result-heading"><h1>AI Review Result</h1><p role="status">Review Failed · {state.selected || state.file?.name || 'Selected source'}</p></header><p className="warning" role="alert"><strong>{guidance.title}</strong> — {guidance.message}</p><section className="result-grid" aria-label="Review results"><article className="result-card"><div className="result-card-title"><ResultIcon name="defender"/><div><h2>Defender</h2><p>Proposal unavailable.</p></div></div><p className="result-empty">No completed proposal was returned.</p></article><article className="result-card"><div className="result-card-title"><ResultIcon name="challenger"/><div><h2>Challenger</h2><p>Review unavailable.</p></div></div><p className="result-empty">No completed review was returned.</p></article><article className="result-card result-recommendation"><div className="result-card-title"><ResultIcon name="award"/><div><h2>Final Recommendation</h2><p>Neural Patch Ranker result</p></div></div><p className="result-empty">Neural ranking is unavailable.</p></article></section><section className="result-changes"><h2><ResultIcon name="code"/> What changed</h2><p>Change details are unavailable.</p></section><div className="result-actions">{['View Original Code', 'View Proposed Patch', 'Compare Changes'].map(label => <button className="button secondary" type="button" disabled key={label}>{label}</button>)}</div><p className="result-safety">Review before applying. Patch is suggested, not auto-applied.</p><p>No automatic retry was started. Retry starts a new review and may use additional provider calls.</p><div className="result-actions"><button className="button primary" type="button" disabled={!!state.busy || !state.consent || state.reviewError.category === 'missing_file'} onClick={state.runReview}>Retry review</button><Link className="button secondary" to={state.reviewError.category === 'missing_file' ? '/scan' : '/results'}>{state.reviewError.category === 'missing_file' ? 'Select a file' : 'Back to scan results'}</Link></div></main>;
    return <main className="site-wrap workspace"><h1>AI Review Result</h1><p role="status">{state.busy === 'review' ? 'Review in progress.' : guidance ? `Failed: ${guidance.message}` : 'No review is available yet.'}</p><Link className="button secondary" to="/ai-review">Back to AI review</Link></main>;
  }
  if (review.review_mode === 'exploratory') return <ExploratoryResults review={review}/>;
  const rounds = review.rounds || [];
  const round = rounds.find(item => item.round === state.round) || rounds[0];
  const ranking = reviewRanking(review.neural_ranking, rounds, review.original_code);
  const selected = ranking.status === 'preferred' ? rounds.find(item => item.round === ranking.winner) : round;
  const eligible = selected && typeof selected.proposed_code === 'string' && selected.proposed_code.trim() && selected.candidate_assessment?.ranking_eligible !== false && proposalStatus(selected, review.original_code, rounds) === 'changed';
  const partial = review.review_status !== 'complete' || review.refinement_status === 'partial';
  const failedStage = review.review_failure?.stage || review.refinement_failure?.stage;
  const stageLabel = { defender_generation: 'Defender proposal', static_verification: 'Static verification', challenger_review: 'Challenger review' }[failedStage];
  const validCount = ranking.status === 'single' ? 1 : ranking.status === 'none' ? 0 : ['preferred', 'tie'].includes(ranking.status) ? ranking.candidates.length : 'Unavailable';
  const complete = !partial && round?.round_status === 'complete' && round?.challenger_status === 'complete';
  const defender = reviewPoints(round?.defender_explanation), challenger = reviewPoints(round?.challenger_feedback);
  const diff = eligible && typeof review.original_code === 'string' ? lineDiff(review.original_code, selected.proposed_code) : null;
  const changeCount = (type, label) => {
    const count = diff.operations.filter(item => item.type === type).length;
    return `${count} ${count === 1 ? 'line' : 'lines'} ${label}${diff.coarse ? ' (approximate)' : ''} in the reviewed scope.`;
  };
  const changes = diff ? [
    changeCount('add', 'added'), changeCount('remove', 'removed'),
    ...(selected.verification?.target_rule_still_reported != null ? [staticOutcome(review.bandit_before, selected.bandit_after, selected.verification)] : []),
  ] : [];
  const action = (label, target, enabled) => enabled ? <Link className={`button ${target === 'proposed' ? 'primary' : 'secondary'}`} to="/code-review" onClick={() => { if (selected) state.setRound(selected.round); state.setCodeTarget?.(target); }}><ActionIcon target={target}/>{label}</Link> : <button className="button secondary" type="button" disabled title="Required source or eligible patch is unavailable"><ActionIcon target={target}/>{label}</button>;
  return <main className="site-wrap workspace result-page">
    <header className="result-heading"><h1>AI Review Result</h1><p role="status"><span aria-hidden="true">{complete ? '\u2713' : '\u25cb'}</span> {complete ? 'Defender and Challenger completed the review' : partial ? 'Partially complete. Available results are shown.' : 'Review completion details are unavailable.'}</p><p>{review.selected_file || review.filename}{review.scope?.cell_index != null ? ` - notebook cell ${review.scope.cell_index + 1}` : ''}</p><p>Targeted issue: {issueName(review.target_finding || review.bandit_before?.[0])}</p></header>
    {review.refinement_status === 'partial' && <p className="warning">{review.refinement_failure?.category === 'invalid_python' ? 'Patch 1 is ready. The second version could not be validated.' : review.refinement_error || 'The second review did not complete.'}</p>}
    {(review.review_failure?.message || review.refinement_failure?.category) && <p className="warning">{review.review_failure?.message || providerError(review.refinement_failure.category).message}</p>}
    {partial && stageLabel && <p className="warning">{review.refinement_failure ? 'Round 2' : 'Round 1'}: {stageLabel} did not complete.</p>}
    {state.reviewError && <p className="warning" role="alert"><strong>Latest retry failed:</strong> {providerError(state.reviewError.category, state.reviewError.message).message} The previous result is preserved.</p>}
    {partial && (state.reviewError?.category || review.review_failure?.category || review.refinement_failure?.category) && state.consent && <div className="result-retry"><p>{providerError(state.reviewError?.category || review.review_failure?.category || review.refinement_failure?.category, state.reviewError?.message || review.review_failure?.message || review.refinement_error).message}</p><button type="button" className="button secondary" disabled={!!state.busy} onClick={state.runReview}>Retry AI review</button><small>Retry starts a new review and may use additional provider calls.</small></div>}
    {rounds.length > 1 && <div className="rounds" role="group" aria-label="Review round">{rounds.map(item => <button type="button" key={item.round} className="button secondary" aria-pressed={round?.round === item.round} onClick={() => state.setRound(item.round)}>Round {item.round}</button>)}</div>}
    <section className="result-grid" aria-label="Review results">
      <article className="result-card"><div className="result-card-title"><ResultIcon name="defender"/><div><h2>Defender</h2><p>Proposed a fix to address the issue.</p></div></div>{defender.length ? <ul>{defender.map((text, i) => <li key={i}>{text}</li>)}</ul> : <p className="result-empty">Defender explanation is unavailable.</p>}</article>
      <article className="result-card"><div className="result-card-title"><ResultIcon name="challenger"/><div><h2>Challenger</h2><p>Reviewed the fix and identified risks.</p></div></div>{challenger.length ? <ul>{challenger.map((text, i) => <li key={i}>{text}</li>)}</ul> : <p className="result-empty">Challenger review is unavailable.</p>}</article>
      <article className="result-card result-recommendation"><div className="result-card-title"><ResultIcon name="award"/><div><h2>Final Recommendation</h2><p>Neural Patch Ranker result</p></div></div>{ranking.status === 'preferred' ? <p className="result-banner">Recommended Patch: Patch {ranking.winner}</p> : <p className="result-empty">{ranking.status === 'single' ? 'Only one eligible patch is available. A comparison is unavailable.' : ranking.status === 'tie' ? 'Both patches received the same score; no unique recommendation.' : ranking.status === 'none' ? 'No eligible patches available for comparison.' : 'Neural ranking is unavailable.'}</p>}{(ranking.status === 'none' || ranking.status === 'single') && <CandidateEligibility rounds={rounds}/>} {ranking.candidates.map(candidate => <div className={`result-score${ranking.status === 'preferred' && ranking.winner === candidate.round ? ' is-preferred' : ''}`} key={candidate.round}><div><strong>Patch {candidate.round}{ranking.status === 'preferred' && ranking.winner === candidate.round ? ' (Recommended)' : ''}</strong><span>Score {candidate.score}</span></div><div className="result-track" aria-hidden="true"><span style={{width: `${candidate.position == null ? 50 : candidate.position * 100}%`}}/></div></div>)}<p className="result-note">Model preference does not establish correctness or security; scores are not probabilities.</p></article>
    </section>
    <section className="result-changes"><h2><ResultIcon name="code"/> What changed</h2>{changes.length ? <ul>{changes.map((change, i) => <li key={i}><span aria-hidden="true">&#x2713;</span>{change}</li>)}</ul> : <p>Change details are unavailable for an eligible patch.</p>}</section>
    <div className="result-actions">{action('View Original Code', 'original', typeof review.original_code === 'string' && !!round)}{action('View Proposed Patch', 'proposed', !!eligible)}{action('Compare Changes', 'compare', !!eligible && typeof review.original_code === 'string')}</div>
    <p className="result-safety">Review before applying. Patch is suggested, not auto-applied.</p>
    <details className="simple-technical"><summary>Technical details</summary><div className="technical-content"><p>Scope: {review.scope?.kind || 'unavailable'}{review.scope?.start_line != null ? `, lines ${review.scope.start_line}\u2013${review.scope.end_line}` : ''}.</p><p>Defender: {round?.defender_explanation || 'Not available.'}</p><p>Challenger: {round?.challenger_feedback || 'Not available.'}</p><p>Suggested tests: {Array.isArray(round?.suggested_tests) ? round.suggested_tests.length : 'Unavailable'}; {round?.suggested_tests?.join('; ') || 'None available.'} Tests executed: No.</p><p>Verification: {round?.verification?.verification_status || 'Not checked'}; syntax: {String(round?.verification?.syntax_valid ?? 'not checked')}. The patch has not been applied.</p><p>AI review attempts: {rounds.length + (review.refinement_status === 'partial' && rounds.length === 1 ? 1 : 0)}. Changed proposals: {typeof review.original_code === 'string' ? rounds.filter(item => proposalStatus(item, review.original_code, rounds) === 'changed').length : 'Unavailable'}. Valid ranking candidates: {validCount}. {round && proposalStatus(round, review.original_code, rounds) === 'unchanged' ? 'No new patch generated.' : ''}</p><CandidateEligibility rounds={rounds}/></div></details>
  </main>;
}

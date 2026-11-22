import React, { useEffect, useState } from 'react';
import { Link } from './navigation.jsx';

export function rankerComparison(candidates) {
  if (!Array.isArray(candidates) || candidates.length !== 2 || new Set(candidates.map(item => item?.label)).size !== 2 ||
      !candidates.every(item => ['A', 'B'].includes(item?.label) && Number.isFinite(item.score) && Number.isInteger(item.rank) && typeof item.code === 'string' && item.code.trim())) return { winners: [] };
  const high = Math.max(...candidates.map(item => item.score));
  const winners = candidates.filter(item => item.score === high);
  if (!winners.every(item => item.rank === 1) || candidates.some(item => item.score < high && item.rank !== 2)) return { winners: [] };
  return { winners: winners.map(item => item.label) };
}

export async function copyCandidateCode(code, clipboard) {
  await clipboard.writeText(code);
}

function candidateDescription(candidate, exampleId) {
  const before = candidate.before_rules, after = candidate.after_rules;
  if (exampleId === 'eval_numbers' && Array.isArray(before) && before.includes('B307') && Array.isArray(after)) {
    if (/\bint\s*\(s\)/.test(candidate.code) && !after.includes('B307')) return 'Uses int(s). Bandit no longer reports the original eval finding.';
    if (/\beval\s*\(s\)/.test(candidate.code) && after.includes('B307')) return 'Uses eval(s). Bandit still reports the original eval finding.';
  }
  return 'A predefined Python candidate checked by Bandit.';
}

export function RankerDemoView({ result }) {
  const [copyStatus, setCopyStatus] = useState('');
  const { winners } = rankerComparison(result?.candidates);
  if (!winners.length) return <p className="error" role="alert">The model comparison is unavailable. Please try again later.</p>;
  const preferred = winners.length === 1 ? winners[0] : null;
  async function copy(code, label) {
    try { await copyCandidateCode(code, navigator.clipboard); setCopyStatus(`Patch ${label} copied.`); }
    catch { setCopyStatus('Copy failed. Select the code manually.'); }
  }
  return <>
    <section className="demo-result" aria-labelledby="demo-result-title"><span className="report-kicker">WHICH PATCH DID AI PREFER?</span>
      <h2 id="demo-result-title">{preferred ? `Model prefers Patch ${preferred}` : 'The model ranked both patches equally'}</h2>
      <p>{preferred ? 'The experimental AI model ranked this patch above the alternative.' : 'The experimental AI model gave both patches the same score.'}</p>
      <span className="demo-winner-badge">{preferred ? 'Rank 1 - Model preference' : 'Equal rank - no preferred patch'}</span>
    </section>
    <section aria-labelledby="demo-compare-title"><div className="demo-section-head"><span className="report-kicker">WHAT DOES EACH PATCH DO?</span><h2 id="demo-compare-title">Compare the code</h2></div>
      <div className="demo-simple-grid">{[...result.candidates].sort((a,b) => a.label.localeCompare(b.label)).map(candidate => {
        const winner = preferred === candidate.label;
        return <article className={`demo-simple-card ${winner ? 'is-winner' : ''}`} key={candidate.label}>
          <div className="demo-card-header"><div><span className="report-kicker">CANDIDATE {candidate.label}</span><h3>Patch {candidate.label}</h3></div><span className="demo-rank">Rank {candidate.rank}</span></div>
          {winner && <p className="demo-preferred-label">Model's preferred patch</p>}
          <p>{candidateDescription(candidate, result.example_id)}</p>
          <div className="demo-code-heading"><strong>Python code</strong><button type="button" className="button secondary" onClick={() => copy(candidate.code, candidate.label)}>Copy code</button></div>
          <pre className="demo-code"><code>{candidate.code}</code></pre>
          <p className="demo-findings">Bandit findings: <strong>{candidate.before_count ?? 'not checked'}</strong> before / <strong>{candidate.after_count ?? 'not checked'}</strong> after</p>
        </article>;
      })}</div><p className="muted" aria-live="polite">{copyStatus}</p>
    </section>
    <section className="demo-limitations"><h2>Important limitations</h2><p>Research demo using predefined examples. The model has not been independently validated on real-world patch outcomes.</p><p>{result.dataset_split === 'train' ? 'This example was part of the synthetic training data.' : 'This example is not an independent real-world evaluation.'} Tests were not run and no patch was applied.</p></section>
    <details className="demo-technical"><summary>How was this ranking calculated?</summary><div><p>Model: {result.model_version || 'Unavailable'}. Scores are raw model outputs, not probabilities or security ratings.</p><p>Stated requirement: {result.requirement}</p>{result.candidates.map(candidate => <p key={candidate.label}>Patch {candidate.label}: raw score {candidate.score}; rank {candidate.rank}; syntax {candidate.syntax_valid === true ? 'valid' : candidate.syntax_valid === false ? 'invalid' : 'not checked'}; Bandit {candidate.before_count ?? 'not checked'} before and {candidate.after_count ?? 'not checked'} after; introduced findings {candidate.introduced_count ?? 'not checked'}.</p>)}<p>The model uses learned patterns and available static features. The synthetic training example is not an independent evaluation. Functional correctness was not tested.</p><h3>Original synthetic code</h3><pre className="demo-code"><code>{result.original_code}</code></pre></div></details>
    <Link className="button secondary" to="/scan">Back to scanning</Link>
  </>;
}

export function RankerDemo() {
  const [state, setState] = useState({ loading: true, result: null, error: '' });
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/research/neural-ranking-demo', { signal: controller.signal, cache: 'no-store' })
      .then(async response => { const data = await response.json(); if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The local demo is unavailable.'); return data; })
      .then(result => setState({ loading: false, result, error: '' }))
      .catch(error => { if (error.name !== 'AbortError') setState({ loading: false, result: null, error: 'The local demo is unavailable. Check that the backend, scanner and saved model are available.' }); });
    return () => controller.abort();
  }, []);
  return <main className="site-wrap workspace research-demo"><header className="simple-review-header"><span className="report-kicker">LOCAL RESEARCH DEMONSTRATION</span><h1>Neural Patch Ranking · Research Demo</h1><p>A local comparison of two predefined patches.</p></header>{state.loading ? <p role="status">Running local static checks and model inference…</p> : state.error ? <p className="error" role="alert">{state.error}</p> : <RankerDemoView result={state.result}/>}</main>;
}

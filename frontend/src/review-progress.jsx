import React from 'react';
import { Link } from './navigation.jsx';
import { ReviewResults } from './workspace-components.jsx';
import { AIResultsPage } from './simple-review.jsx';

const errorGuidance = {
  missing_file: ['File no longer available', 'Your uploaded file is no longer available. Please select it again to continue.'],
  authentication: ['Authentication or access failed', 'Check the API key and model access in your local configuration, then retry.'],
  quota_exhausted: ['Provider quota or credits exhausted', 'Check your provider balance and quota, or replace the API key in local configuration, restart the backend and retry.'],
  billing: ['Provider billing or credit issue', 'Check provider billing and credits, or replace the API key in local configuration, restart the backend and retry.'],
  rate_limit: ['Provider rate limit reached', 'Wait a moment and retry, or replace the API key in local configuration and restart the backend.'],
  timeout: ['The provider took too long', 'The review timed out. Try again, or select a smaller finding to review.'],
  transport_timeout: ['The provider took too long', 'The connection timed out. Try again when the provider is available.'],
  provider_gateway_timeout: ['The provider took too long', 'The provider timed out. Try again when it is available.'],
  timeout_or_interruption: ['Review interrupted', 'The request timed out or was interrupted. Retry when you are ready.'],
  truncated_response: ['The provider response was incomplete', 'The model stopped before finishing. Try a smaller code region or another configured model.'],
  json_parse: ['The provider returned invalid JSON', 'The review could not read the model response. Try again or choose another model.'],
  schema_validation: ['The provider response was incomplete or invalid', 'The response was missing required information or contained invalid fields. Try again.'],
  invalid_envelope: ['The provider response was incomplete or invalid', 'The provider response could not be interpreted. Try again.'],
  invalid_review_stream: ['The review response was invalid', 'The review response could not be read. Try again.'],
  incomplete_review_stream: ['The review response was incomplete', 'The connection ended before a result was received. Try again.'],
  review_stream_too_large: ['The review response was too large', 'The response exceeded the review limit. Try a smaller selection.'],
  response_too_large: ['The provider response was too large', 'The response exceeded the review limit. Try a smaller selection.'],
  unsupported_finish: ['The provider response was incomplete or incompatible', 'The provider did not return a usable review. Try again.'],
  invalid_python: ['The proposed code is not valid Python', 'The provider returned code that failed the syntax check. Retry or select a smaller region.'],
  empty_response: ['The provider returned no content', 'No usable response was received. Try again or choose another model.'],
  provider_http: ['The provider is unavailable', 'The upstream provider returned an error. Wait and try again.'],
  provider_error: ['The provider is unavailable', 'The upstream provider could not complete the review. Try again.'],
  transport_error: ['Could not reach the provider', 'Check the network connection and try again.'],
  connection_error: ['Connection interrupted', 'The review connection failed. Check the backend and retry.'],
  provider_request: ['The provider rejected the request', 'Check the configured model, input context and output limits before retrying.'],
  unsupported_input: ['This input cannot be reviewed', 'Choose an eligible Python file or notebook code cell and try again.'],
  input_too_large: ['The selected input is too large', 'Choose a smaller file or select a finding to review a bounded region.'],
  configuration: ['Provider configuration needs attention', 'Check the API base URL, key and model in the local configuration.'],
  context_limit: ['The review context is too large', 'Choose a smaller finding or review the available proposal manually.'],
};

export function providerError(category, fallback) {
  const known = errorGuidance[category];
  return known ? { title: known[0], message: known[1] } : { title: 'Review could not be completed', message: fallback || 'Try again when you are ready.' };
}

// Percentages count completed workflow milestones, not elapsed time or model tokens.
const milestones = [
  ['request_accepted', 'Preparing selected source', 5, 3],
  ['source_prepared', 'Selected source is ready', 20, 10],
  ['defender_started', 'Defender is generating a patch', 20, 10],
  ['defender_completed', 'Defender proposal completed', 40, 20],
  ['verification_started', 'Comparing static findings', 40, 20],
  ['verification_completed', 'Static comparison completed', 55, 30],
  ['challenger_started', 'Challenger is reviewing the proposal', 55, 30],
  ['challenger_completed', 'Challenger review completed', 90, 40],
  ['round2_defender_started', 'Round 2: Defender is refining the patch', 90, 40],
  ['round2_defender_completed', 'Round 2: Defender proposal completed', 90, 55],
  ['round2_verification_started', 'Round 2: comparing static findings', 90, 55],
  ['round2_verification_completed', 'Round 2: static comparison completed', 90, 70],
  ['round2_challenger_started', 'Round 2: Challenger is reviewing', 90, 70],
  ['round2_challenger_completed', 'Round 2: Challenger review completed', 90, 90],
];

export function advanceProgress(current, stage, refine) {
  const index = milestones.findIndex(item => item[0] === stage);
  if (index < 0) return { index: current?.index ?? -1, label: 'Review in progress', percent: null, events: current?.events || [] };
  if (index < (current?.index ?? -1)) return current;
  const item = milestones[index];
  return { index, label: item[1], percent: item[refine ? 3 : 2], events: [...new Set([...(current?.events || []), stage])] };
}

export function BattleActivity({ progress, refine }) {
  const events = progress?.events || [];
  const status = (round, agent) => {
    const prefix = round === 2 ? 'round2_' : '';
    if (events.includes(`${prefix}${agent}_completed`)) return 'Completed';
    if (events.includes(`${prefix}${agent}_started`)) return 'In progress';
    return 'Waiting';
  };
  return <section className="battle-activity" aria-label="AI battle activity"><h2>Defender vs Challenger</h2>{(refine ? [1, 2] : [1]).map(round => <div className="battle-round" key={round}><h3>Round {round}</h3><div className="battle-agents">{[['defender', 'Defender'], ['challenger', 'Challenger']].map(([key, label]) => <div className="battle-agent" key={key}><strong>{label}</strong><span>{status(round, key)}</span></div>)}</div></div>)}</section>;
}

export function ProgressPage({ state }) {
  if (state.reviewError) return <AIResultsPage state={state}/>;
  if (!state.file && !state.review && state.busy !== 'review') return <main className="progress-screen"><div className="progress-content" role="alert"><h1>No review in progress</h1><p>Your uploaded file is no longer available. Please select it again to continue.</p><Link className="button primary" to="/scan">Select a file</Link></div></main>;
  if (state.busy !== 'review') return <main className="progress-screen"><div className="progress-content"><div className="progress-icon">◇</div><h1>No review in progress</h1><p>A review starts only when you choose Run AI Review.</p><Link className="button primary" to={state.review ? '/ai-review/results' : '/ai-review'}>{state.review ? 'View review results' : 'Go to review form'}</Link></div></main>;
  const progress = state.progress;
  const label = progress?.label || '';
  const currentStage = /Defender/i.test(label) ? 'Defender' : /static|verification/i.test(label) ? 'Verify' : /Challenger/i.test(label) ? 'Challenger' : /final/i.test(label) ? 'Finalize' : progress?.index >= 0 ? 'Prepare' : null;
  return <main className="progress-screen"><div className="progress-content"><div className="progress-icon"><svg viewBox="0 0 64 64" aria-hidden="true"><path d="M32 7 51 14v15c0 13-8 22-19 28C21 51 13 42 13 29V14L32 7Z"/><path d="m23 31 6 6 13-14"/></svg></div><span className="progress-eyebrow">AI REVIEW IN PROGRESS</span><h1>Analyzing your code</h1><p className="progress-filename">{state.selected}</p><div className="progress-stage" role="status" aria-live="polite"><span className="activity-dot"/><strong>{progress?.label || 'Connecting to the review service'}</strong></div><BattleActivity progress={progress} refine={state.refine}/><ol className="milestone-nav" aria-label="Review stages">{['Prepare', 'Defender', 'Verify', 'Challenger', 'Finalize'].map(stage => <li key={stage} aria-current={currentStage === stage ? 'step' : undefined}><span aria-hidden="true"/>{stage}</li>)}</ol><div className="progress-meta"><span>Workflow progress</span><span>{progress?.percent == null ? 'In progress' : `${progress.percent}%`}</span></div><div className={`progress-track ${progress?.percent == null ? 'indeterminate' : ''}`} role="progressbar" aria-label="Workflow progress" aria-valuemin={0} aria-valuemax={100} {...(progress?.percent == null ? {} : { 'aria-valuenow': progress.percent })}><div style={progress?.percent == null ? undefined : { width: `${progress.percent}%` }}/></div><p className="progress-help">Progress reflects confirmed review stages, not remaining time. Provider calls may take a moment.</p><div className="progress-privacy">◇ &nbsp; Only your selected source is sent for the review you authorized. Generated code is not applied.</div></div></main>;
}

export { AIResultsPage } from './simple-review.jsx';

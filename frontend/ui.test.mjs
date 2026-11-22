import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { request, streamReview } from './src/api.js';
import { lineDiff, splitDiffRows } from './src/diff.js';

let server;
let components;
const noop = () => {};

before(async () => {
  server = await createServer({ configFile: false, logLevel: 'silent', appType: 'custom', server: { middlewareMode: true } });
  components = await server.ssrLoadModule('/src/main.jsx');
});

after(async () => { if (server) await server.close(); });

test('battle activity reports only confirmed agent events for authorized rounds', async () => {
  const { advanceProgress, BattleActivity } = await server.ssrLoadModule('/src/review-progress.jsx');
  let progress = advanceProgress(null, 'defender_started', true);
  progress = advanceProgress(progress, 'defender_completed', true);
  progress = advanceProgress(progress, 'challenger_started', true);
  const markup = renderToStaticMarkup(React.createElement(BattleActivity, { progress, refine: true }));
  assert.match(markup, /Round 1/); assert.match(markup, /Round 2/);
  assert.match(markup, /Defender<\/strong><span>Completed/); assert.match(markup, /Challenger<\/strong><span>In progress/);
  assert.match(markup, /Waiting/);
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(BattleActivity, { progress, refine: false })), /Round 2/);
});

test('failed reviews retain the results layout and require explicit retry', async () => {
  const { ProgressPage } = await server.ssrLoadModule('/src/review-progress.jsx');
  for (const [category, message] of [['rate_limit', /rate limit/i], ['billing', /billing/i], ['authentication', /authentication/i], ['transport_timeout', /timed out/i], ['json_parse', /invalid JSON/i]]) {
    const markup = renderToStaticMarkup(React.createElement(ProgressPage, {state:{reviewError:{category},selected:'example.py',consent:true,busy:'',runReview:noop}}));
    assert.match(markup, message); assert.match(markup, /Defender/); assert.match(markup, /Challenger/); assert.match(markup, /Final Recommendation/);
    assert.match(markup, /Retry review/); assert.match(markup, /No automatic retry/); assert.doesNotMatch(markup, /Recommended Patch: Patch/);
  }
});

test('partial review identifies the incomplete stage and preserves earlier output after a failed retry', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const review = {review_mode:'patch',review_status:'partial',original_code:'x=1',rounds:[{round:1,round_status:'partial',proposed_code:'x=2',defender_explanation:'First proposal.',challenger_status:'unavailable',candidate_assessment:{ranking_eligible:false,reasons:['invalid_or_unchecked_syntax']}}],review_failure:{stage:'challenger_review',category:'rate_limit'},neural_ranking:{status:'no_valid_candidates'}};
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,round:1,setRound:noop,consent:true,runReview:noop,reviewError:{category:'authentication'}}}));
  assert.match(markup,/Round 1: Challenger review did not complete/); assert.match(markup,/First proposal/);
  assert.match(markup,/Latest retry failed/); assert.match(markup,/API key and model access/); assert.match(markup,/previous result is preserved/);
  assert.match(markup,/Python syntax is invalid or was not checked/); assert.doesNotMatch(markup,/Recommended Patch: Patch/);
});

test('Round 2 truncation explains the failure and keeps Patch 1 inspectable', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const review = {review_mode:'patch', review_status:'complete', original_code:'x=1',
    rounds:[{round:1, round_status:'complete', challenger_status:'complete', proposed_code:'x=2', defender_explanation:'First proposal.'}],
    refinement_status:'partial', refinement_failure:{stage:'defender_generation', category:'truncated_response'},
    refinement_error:'Second-round defender generation: Hosted AI response was truncated.',
    neural_ranking:{status:'single_candidate', candidates:[]}};
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,round:1,setRound:noop,consent:true,runReview:noop}}));
  assert.match(markup,/Second-round defender generation: Hosted AI response was truncated/);
  assert.match(markup,/The model stopped before finishing/);
  assert.match(markup,/First proposal/);
  assert.match(markup,/<a[^>]*href="\/code-review"[^>]*>.*?View Proposed Patch<\/a>/);
  assert.match(markup,/Only one eligible patch/);
  assert.doesNotMatch(markup,/Recommended Patch: Patch/);
});

test('public and workspace URLs render distinct pages and helpful empty states', () => {
  for (const [path, expected] of [['/', /Find the/], ['/features', /A clearer path/],
    ['/how-it-works', /A review you can follow/], ['/about', /final-year project prototype/], ['/faq', /Frequently asked questions/],
    ['/privacy', /Know what happens to your code/], ['/scan', /Upload source/], ['/results', /No scan results yet/],
    ['/ai-review', /Scan a file first/], ['/code-review', /No proposal to compare yet/], ['/missing', /PAGE NOT FOUND/]]) {
    const markup = renderToStaticMarkup(React.createElement(components.App, { initialPath: path }));
    assert.match(markup, expected, path);
    assert.match(markup, /href="\/scan"/);
  }
  const home = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/' }));
  assert.doesNotMatch(home, /Upload source/);
  const scan = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/scan' }));
  assert.doesNotMatch(scan, /Defender proposes/);
});

test('navigation has usable links, active styles and an accessible mobile menu', () => {
  const markup = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/features' }));
  assert.match(markup, /href="\/features" aria-current="page"/);
  assert.match(markup, /aria-expanded="false" aria-controls="primary-navigation"/);
  for (const path of ['/features', '/how-it-works', '/about', '/faq', '/privacy', '/scan']) assert.ok(markup.includes(`href="${path}"`));
  const open = renderToStaticMarkup(React.createElement(components.Header, { initiallyOpen: true }));
  assert.match(open, /aria-expanded="true"/);
  assert.match(open, /primary-nav open/);
});

test('home introduces the review workflow without fabricated results', () => {
  const markup = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/' }));
  for (const label of ['Challenge the', 'Python security scanning', 'ZIP project analysis', 'Notebook code analysis', 'Defender patch proposals', 'Challenger independent review', 'Code comparison &amp; verification']) assert.ok(markup.includes(label), label);
  assert.match(markup, /ILLUSTRATIVE WORKFLOW/);
  assert.match(markup, /Human review/);
});

test('public workflow and about content have structured, distinct sections', () => {
  const workflow = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/how-it-works' }));
  assert.equal((workflow.match(/class="step-card"/g) || []).length, 4);
  assert.match(workflow, /Choose your scope/); assert.match(workflow, /Inspect, then decide/);
  const about = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/about' }));
  assert.match(about, /about-grid/); assert.match(about, /Our mission/); assert.match(about, /Who it is for/);
});

test('history navigation handles forward and back without storing workspace data', async () => {
  const { createNavigator } = await server.ssrLoadModule('/src/navigation.jsx');
  let listener, disposed = false;
  const calls = [], browser = { location: { pathname: '/' }, history: { pushState(state, title, path) { calls.push([state, path]); browser.location.pathname = path; } },
    addEventListener(name, callback) { assert.equal(name, 'popstate'); listener = callback; },
    removeEventListener(name, callback) { disposed = name === 'popstate' && callback === listener; }, scrollTo: noop };
  const seen = [], navigator = createNavigator(browser, path => seen.push(path));
  navigator.go('/scan'); navigator.go('/results'); browser.location.pathname = '/scan'; listener(); browser.location.pathname = '/results'; listener();
  assert.deepEqual(seen, ['/scan', '/results', '/scan', '/results']);
  assert.deepEqual(calls, [[null, '/scan'], [null, '/results']]);
  navigator.dispose(); assert.ok(disposed);
});

test('project files display findings and selection with size limits', () => {
  const scan = { filename: 'project.zip', total_findings: 1, findings: [{ severity: 'HIGH' }],
    findings_by_file: { 'src/a.py': [{ test_id: 'B307', severity: 'HIGH', line_number: 2, description: 'Avoid eval' }], 'large.py': [] },
    file_sizes: { 'src/a.py': 20, 'large.py': 40000 } };
  const markup = renderToStaticMarkup(React.createElement(components.ScanResults, { scan, selected: 'src/a.py' }));
  assert.match(markup, /src\/a.py/); assert.match(markup, /B307/); assert.match(markup, /HIGH/);
  assert.match(markup, /aria-pressed="true"/); assert.match(markup, /large.py/);
});

test('scan report explains zero findings and incomplete notebook coverage', async () => {
  const { ScanReport } = await server.ssrLoadModule('/src/scan-report.jsx');
  const scan = { filename: 'demo.ipynb', scan_type: 'notebook', scan_status: 'partial', total_findings: 0,
    findings: [], analyzed_cells: 1, findings_by_file: { 'demo.ipynb · cell 1': [] },
    file_sizes: { 'demo.ipynb · cell 1': 25 }, review_targets: { 'demo.ipynb · cell 1': { path: 'demo.ipynb', cell_index: 0 } },
    skipped: [{ path: 'demo.ipynb', cell_index: 1, reason: 'Notebook magic or shell syntax is not analyzed.' }] };
  const markup = renderToStaticMarkup(React.createElement(ScanReport, { scan, file: { name: 'demo.ipynb', size: 200 }, onReview: noop }));
  assert.match(markup, /No security issues were reported in the code that was analyzed/);
  assert.match(markup, /does not guarantee the code is secure/); assert.match(markup, /Partial scan/);
  assert.match(markup, /code cell 2/); assert.match(markup, /magic or shell syntax/);
  assert.match(markup, /Explore this code with AI/); assert.doesNotMatch(markup, /Review with AI/);
  assert.doesNotMatch(markup, /Review code cell with AI/);
});

test('measured scan bars use real totals and omit unmeasurable coverage', async () => {
  const { ScanReport } = await server.ssrLoadModule('/src/scan-report.jsx');
  const scan = { filename: 'p.zip', scan_type: 'zip_project', scan_status: 'completed', total_findings: 3,
    findings: [{severity: 'HIGH', test_id: 'B307'}, {severity: 'HIGH', test_id: 'B608'}, {severity: 'LOW', test_id: 'B324'}], eligible_source_files: 2, analyzed_source_files: 2 };
  const render = value => renderToStaticMarkup(React.createElement(ScanReport, { scan: value, file: {name:'p.zip'}, onReview:noop }));
  const markup = render(scan);
  assert.match(markup, /aria-valuenow="66.7" aria-valuetext="2 of 3 findings"/);
  assert.match(markup, /aria-valuenow="0" aria-valuetext="0 of 3 findings"/);
  assert.match(markup, /aria-label="Coverage"[^>]*aria-valuenow="100" aria-valuetext="2 of 2 supported files"/);
  for (const change of [{scan_status:'partial'}, {eligible_source_files:0}, {analyzed_source_files:3}, {analyzed_source_files:null}]) {
    assert.doesNotMatch(render({...scan, ...change}), /role="progressbar" aria-label="Coverage"/);
  }
});

test('relative neural scores handle negatives and ties without reliability claims', async () => {
  const { NeuralRanking } = await server.ssrLoadModule('/src/simple-review.jsx');
  const rounds = [{round:1, proposed_code:'a'}, {round:2, proposed_code:'b'}];
  const render = scores => renderToStaticMarkup(React.createElement(NeuralRanking, {rounds, setRound:noop,
    ranking:{status:'available', candidates:scores.map((score,i) => ({round:i+1, rank:i+1, score}))}}));
  const negative = render([-4, -2]);
  assert.match(negative, /Model prefers Patch 1/); assert.doesNotMatch(negative, /reliability %/);
  const tie = renderToStaticMarkup(React.createElement(NeuralRanking, {rounds, ranking:{status:'available',candidates:[{round:1,rank:1,score:0},{round:2,rank:1,score:0}]}}));
  assert.match(tie, /tie/); assert.doesNotMatch(tie, /Model prefers/);
});

test('scan report preselects one finding and review actions preserve source and line', async () => {
  const { ScanReport, suggestedSelection } = await server.ssrLoadModule('/src/scan-report.jsx');
  const finding = { file_path: 'pkg/demo.ipynb', cell_index: 2, line_number: 7, test_id: 'B307', severity: 'MEDIUM', description: 'Use of eval' };
  const scan = { filename: 'p.zip', scan_type: 'zip_project', scan_status: 'completed', total_findings: 1,
    findings: [finding], eligible_source_files: 1, analyzed_source_files: 1, findings_by_file: { 'pkg/demo.ipynb · cell 3': [finding] },
    review_targets: { 'pkg/demo.ipynb · cell 3': { path: 'pkg/demo.ipynb', cell_index: 2 } }, file_sizes: { 'pkg/demo.ipynb · cell 3': 30 } };
  assert.deepEqual(suggestedSelection(scan, { name: 'p.zip' }), { source: 'pkg/demo.ipynb · cell 3', line: 7 });
  const { IssueRow } = await server.ssrLoadModule('/src/scan-report.jsx');
  const choices = [], tree = IssueRow({ item: finding, scan, file: { name: 'p.zip' }, onReview: (...args) => choices.push(args), busy: false });
  const visit = node => { if (Array.isArray(node)) return node.forEach(visit); if (!node || typeof node !== 'object') return;
    if (node.type === 'button') node.props.onClick(); visit(node.props?.children); };
  visit(tree); assert.deepEqual(choices, [[Object.keys(scan.review_targets)[0], 7, 'B307']]);
  const markup = renderToStaticMarkup(React.createElement(ScanReport, { scan, file: { name: 'p.zip' }, onReview: noop }));
  assert.match(markup, /code cell 3/); assert.match(markup, /line 7/); assert.match(markup, /Review with AI/);
});

test('complete zero findings provide exploratory action without inventing a finding', async () => {
  const { ScanReport } = await server.ssrLoadModule('/src/scan-report.jsx');
  const scan = { filename: 'clean.py', scan_status: 'completed', total_findings: 0, findings: [] };
  const markup = renderToStaticMarkup(React.createElement(ScanReport, { scan, file: { name: 'clean.py', size: 12 }, onReview: noop }));
  assert.match(markup, /Scan another file/); assert.match(markup, /Explore this code with AI/);
  assert.doesNotMatch(markup, /Review this issue with AI/); assert.doesNotMatch(markup, /Partial scan/);
});

test('unified ZIP findings use one automatic bounded review and list coverage honestly', async () => {
  const { ScanReport, suggestedSelection } = await server.ssrLoadModule('/src/scan-report.jsx');
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const findings = [{ file_path: 'src/a.py', line_number: 8, test_id: 'B307', severity: 'HIGH', description: 'First issue' },
    { file_path: 'notes.ipynb', cell_index: 1, line_number: 3, test_id: 'B602', severity: 'MEDIUM', description: 'Second issue' }];
  const scan = { filename: 'p.zip', scan_type: 'zip_project', scan_status: 'completed', total_findings: 2, findings,
    eligible_source_files: 2, analyzed_source_files: 2, findings_by_file: { 'src/a.py': [findings[0]], 'notes.ipynb · cell 2': [findings[1]], 'empty.py': [] },
    review_targets: { 'src/a.py': { path: 'src/a.py', cell_index: null }, 'notes.ipynb · cell 2': { path: 'notes.ipynb', cell_index: 1 }, 'empty.py': { path: 'empty.py', cell_index: null } },
    file_sizes: { 'src/a.py': 9000, 'notes.ipynb · cell 2': 20, 'empty.py': 10 } };
  assert.deepEqual(suggestedSelection(scan, { name: 'p.zip' }), { source: 'src/a.py', line: 8 });
  const report = renderToStaticMarkup(React.createElement(ScanReport, { scan, file: { name: 'p.zip' }, onReview: noop }));
  assert.match(report, /First issue/); assert.match(report, /Second issue/); assert.doesNotMatch(report, /empty.py/);
  assert.equal((report.match(/>Review with AI<\/button>/g) || []).length, 3); assert.match(report, /selected bounded code region/);
  assert.match(report, /<details class="scan-findings"><summary>View scan findings/);
  const review = { filename: 'p.zip', selected_file: 'src/a.py', original_code: 'x=1', review_status: 'complete',
    scope: { kind: 'finding', start_line: 5, end_line: 10, finding_line: 8, cell_index: null },
    bandit_before: [{ ...findings[0], line_number: 4 }], rounds: [{ round: 1, proposed_code: 'x=2', defender_explanation: 'Change.', challenger_feedback: 'Review.', suggested_tests: [], bandit_after: [] }] };
  const result = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { scan, review, round: 1, setRound: noop } }));
  assert.match(result, /src\/a.py/); assert.match(result, /Unsafe code execution/);
  assert.match(result, /lines 5\u201310/); assert.match(result, /Technical details/);
});

test('a notebook with no analyzed cells is not presented as clean', async () => {
  const { ScanReport } = await server.ssrLoadModule('/src/scan-report.jsx');
  const scan = { filename: 'skip.ipynb', scan_type: 'notebook', scan_status: 'partial', total_findings: 0,
    findings: [], analyzed_cells: 0, findings_by_file: {}, skipped: [{ path: 'skip.ipynb', cell_index: 0, reason: 'Notebook magic or shell syntax is not analyzed.' }] };
  const markup = renderToStaticMarkup(React.createElement(ScanReport, { scan, file: { name: 'skip.ipynb', size: 100 }, onReview: noop }));
  assert.match(markup, /No supported code was analyzed/);
  assert.doesNotMatch(markup, /No security issues were detected/);
  assert.doesNotMatch(markup, /Explore this code with AI/);
});

test('ZIP file selection invokes the chosen member only', () => {
  const chosen = [];
  const tree = components.ScanResults({ scan: { filename: 'p.zip', total_findings: 0, findings: [],
    findings_by_file: { 'a.py': [], 'b.py': [] }, file_sizes: { 'a.py': 10, 'b.py': 10 } },
    selected: 'a.py', onSelect: value => chosen.push(value) });
  const visit = node => {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== 'object') return;
    if (node.type === 'button' && node.props.children === 'Select file') node.props.onClick();
    visit(node.props?.children);
  };
  visit(tree);
  assert.deepEqual(chosen, ['b.py']);
});

test('ZIP review requires selection and consent; refinement is optional', () => {
  const props = { file: { name: 'project.zip', size: 100 }, scan: {}, selected: '', busy: '', consent: false,
    setConsent: noop, refine: false, setRefine: noop, runReview: noop };
  const empty = renderToStaticMarkup(React.createElement(components.ReviewSetup, props));
  assert.match(empty, /Select an eligible issue/); assert.match(empty, /disabled/);
  const ready = renderToStaticMarkup(React.createElement(components.ReviewSetup, {...props,selected:'src/a.py',consent:true}));
  assert.match(ready, /src\/a.py/); assert.match(ready, /external AI service/);
  assert.match(empty, /type="checkbox" disabled=""/); assert.doesNotMatch(empty, /type="checkbox"[^>]*checked/);
});

test('partial reviews show selected file, proposal, and unexecuted tests', () => {
  const review = { filename: 'project.zip', selected_file: 'src/a.py', original_code: '<script>old</script>', bandit_before: [], review_status: 'partial',
    review_failure: { message: 'Challenger unavailable.' }, rounds: [{ round: 1, proposed_code: '<script>new</script>',
      defender_explanation: 'Proposal', challenger_feedback: null, suggested_tests: null, bandit_after: null, verification: { verification_status: 'verification_incomplete' } }] };
  const result = renderToStaticMarkup(React.createElement(components.ReviewResults, { review, selectedRound: 1, setSelectedRound: noop, openCode: noop }));
  assert.match(result, /Review incomplete/); assert.match(result, /Not applied/); assert.match(result, /Tests unavailable/);
  const code = renderToStaticMarkup(React.createElement(components.CodeReview, { review, selectedRound: 1, setSelectedRound: noop }));
  assert.match(code, /src\/a.py/); assert.match(code, /Manual review required/i); assert.match(code, /&lt;script&gt;new/);
  assert.doesNotMatch(code, /<script>new/); assert.match(code, /Unavailable/);
  assert.match(code, /Copy Original/); assert.match(code, /Copy Proposed Code/); assert.match(code, /Unified/);
  assert.match(code, /Remaining findings/); assert.match(code, /introduced findings/i);
});

test('request sends selected ZIP member and opt-in headers', async () => {
  const original = globalThis.fetch;
  let call;
  globalThis.fetch = async (path, options) => { call = { path, options }; return { ok: true, json: async () => ({}) }; };
  try {
    await request('/api/ai-review', { file: new Blob(['zip']), member: 'src/a.py', consent: true, refine: true });
    assert.equal(call.options.body.get('member'), 'src/a.py');
    assert.deepEqual(call.options.headers, { 'X-AI-Consent': 'true', 'X-AI-Refine': 'true' });
  } finally { globalThis.fetch = original; }
});

test('review form excludes results even when a previous result exists', () => {
  const state = { scan: { findings: [] }, file: new File(['x = 1'], 'example.py'), selected: 'example.py',
    busy: '', consent: false, setConsent: noop, refine: false, setRefine: noop, runReview: noop,
    review: { rounds: [{ defender_explanation: 'private old proposal' }] }, reviewError: '' };
  const markup = renderToStaticMarkup(React.createElement(components.AIPage, { state }));
  assert.match(markup, /Start AI Review/);
  assert.doesNotMatch(markup, /private old proposal/);
  assert.doesNotMatch(markup, /Challenger review completed/);
});

test('rejected uploads do not show a ready or retry state', () => {
  const state = { file: null, error: 'This file exceeds the 100 MiB limit.', busy: '', choose: noop };
  const markup = renderToStaticMarkup(React.createElement(components.ScanPage, { state }));
  assert.match(markup, /100 MiB limit/); assert.match(markup, /Choose another file/);
  assert.doesNotMatch(markup, /Ready to scan|Retry scan/);
});

test('zero-finding notebook review is read-only and disables refinement', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const review = { filename: 'lesson.ipynb', scope: { cell_index: 0 }, review_mode: 'exploratory',
    exploratory_feedback: 'Check the condition.', suggested_tests: ['Check both branches'],
    rounds: [], refinement_status: 'not_started_no_findings' };
  const result = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1, setRound: noop } }));
  assert.match(result, /Check the condition/); assert.match(result, /notebook cell 1/i);
  assert.doesNotMatch(result, /Compare Changes/);
  const form = renderToStaticMarkup(React.createElement(components.ReviewSetup, {scan:{findings:[]},file:{name:'lesson.ipynb',size:20},selected:'lesson.ipynb',consent:true,setConsent:noop,refine:false,setRefine:noop,runReview:noop,busy:''}));
  assert.match(form, /no patch is requested/i); assert.doesNotMatch(form, /Try a second fix/);
});

test('progress advances only on confirmed milestones with indeterminate fallback', async () => {
  const { advanceProgress, ProgressPage } = await server.ssrLoadModule('/src/review-progress.jsx');
  let progress = advanceProgress(null, 'request_accepted', true);
  assert.equal(progress.percent, 3);
  progress = advanceProgress(progress, 'defender_started', true);
  assert.equal(progress.percent, 10);
  progress = advanceProgress(progress, 'defender_completed', true);
  assert.equal(progress.percent, 20);
  assert.equal(advanceProgress(progress, 'request_accepted', true).percent, 20);
  assert.equal(advanceProgress(progress, 'unknown', true).percent, null);
  assert.ok(advanceProgress(progress, 'round2_challenger_completed', true).percent < 100);
  const markup = renderToStaticMarkup(React.createElement(ProgressPage, { state: { busy: 'review', selected: 'a.py', progress: null } }));
  assert.match(markup, /Analyzing your code/); assert.match(markup, /In progress/);
  assert.doesNotMatch(markup, /aria-valuenow/);
});

test('progress failure requires an explicit retry and results support partial rounds', async () => {
  const { ProgressPage, AIResultsPage } = await server.ssrLoadModule('/src/review-progress.jsx');
  const failed = renderToStaticMarkup(React.createElement(ProgressPage, { state: { reviewError: { category: 'authentication', message: 'Provider rejected access.' }, selected: 'a.py', consent: true, busy: '', runReview: noop } }));
  assert.match(failed, /Authentication or access failed/); assert.match(failed, /Retry review/); assert.match(failed, /No automatic retry/);
  const empty = renderToStaticMarkup(React.createElement(components.App, {initialPath:'/ai-review/results'}));
  assert.match(empty, /No review is available yet/);
  const review = {filename:'project.zip',selected_file:'src/a.py',review_status:'partial',review_failure:{message:'Challenger timed out.'},rounds:[{round:1,proposed_code:'x=1',defender_explanation:'A change.',challenger_feedback:null,suggested_tests:null}]};
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,round:1,setRound:noop}}));
  assert.match(markup,/Partially complete/); assert.match(markup,/src\/a.py/); assert.match(markup,/Challenger timed out/);
});

test('safe provider errors give clear guidance without losing partial proposals', async () => {
  const { providerError, AIResultsPage } = await server.ssrLoadModule('/src/review-progress.jsx');
  for (const category of ['quota_exhausted', 'rate_limit', 'billing']) {
    assert.match(providerError(category).message, /replace the API key/i);
  }
  for (const category of ['authentication', 'timeout', 'truncated_response', 'json_parse', 'schema_validation', 'invalid_python', 'provider_http', 'unsupported_input']) {
    assert.ok(providerError(category).title);
    assert.ok(providerError(category).message);
  }
  const review = { filename: 'a.py', refinement_status: 'partial', refinement_failure: { category: 'quota_exhausted' },
    rounds: [{ round: 1, proposed_code: 'x = 1', defender_explanation: 'A proposal.', challenger_feedback: 'Check inputs.', suggested_tests: [] }] };
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1, setRound: noop } }));
  assert.match(markup, /balance and quota/i); assert.match(markup, /replace the API key/i);
  assert.match(markup, /A proposal/); assert.match(markup, /Partially complete/);
});

test('AI report shows selected scoped issue and actual static verification', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/review-progress.jsx');
  const review = { filename: 'a.py', review_status: 'complete', scope: { kind: 'finding', start_line: 10, end_line: 20, finding_line: 14 },
    bandit_before: [{ line_number: 1, description: 'Other finding' }, { line_number: 5, description: 'Selected finding' }],
    rounds: [{ round: 1, proposed_code: 'x=1', defender_explanation: 'Change the code.', challenger_feedback: 'Consider compatibility.',
      challenger_status: 'complete', suggested_tests: ['Check inputs'], bandit_after: [],
      verification: { syntax_valid: true, verification_status: 'static_improvement', remaining_findings: [], introduced_findings: [] } }] };
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1, setRound: noop, navigate: noop } }));
  assert.match(markup, /Change the code/); assert.match(markup, /lines 10\u201320/); assert.match(markup, /static_improvement/);
  assert.match(markup, /syntax: true/); assert.match(markup, /Tests executed: No/); assert.match(markup, /not been applied/);
});

test('outcomes distinguish unchanged, changed, incomplete and scoped reviews', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const render = review => renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1, setRound: noop } }));
  const round = { round: 1, proposed_code: 'x=1', defender_explanation: 'Check inputs.', challenger_feedback: 'Consider compatibility.', challenger_status: 'complete', suggested_tests: ['Try an input'], bandit_after: [], verification: { syntax_valid: true, verification_status: 'no_static_improvement' } };
  const base = { filename: 'a.py', original_code: 'x=1', bandit_before: [], review_status: 'complete', rounds: [round] };
  const unchanged = render(base);
  assert.match(unchanged, /No new patch generated/); assert.match(unchanged, /Technical details/);
  const changed = render({...base, rounds:[{...round,proposed_code:'x=2'}]}); assert.match(changed,/Compare Changes/);
  const partial = render({...base,review_status:'partial',rounds:[{...round,challenger_feedback:null}]}); assert.match(partial,/Partially complete/); assert.match(partial,/Not available/);
  const scoped = render({...base,selected_file:'src/a.ipynb',scope:{kind:'finding',start_line:2,end_line:8,cell_index:2},rounds:[round,{...round,round:2}]});
  assert.match(scoped,/src\/a.ipynb/); assert.match(scoped,/notebook cell 3/); assert.match(scoped,/Round 2/);
  const failed = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{reviewError:{category:'authentication'}}})); assert.match(failed,/Failed/);
});

test('experimental ranker explains single, unavailable and multiple candidates', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const review = { filename: 'a.py', original_code: 'x=1', bandit_before: [], review_status: 'complete', rounds: [{ round: 1, proposed_code: 'x=2', suggested_tests: [] }, { round: 2, proposed_code: 'x=3', suggested_tests: [] }] };
  const render = ranking => renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review: { ...review, neural_ranking: ranking }, round: 1, setRound: noop } }));
  assert.match(render({status:'single_candidate'}), /Only one eligible patch/);
  assert.match(render({status:'unavailable'}), /Neural ranking is unavailable/);
  const ranked = render({status:'available',candidates:[{round:2,rank:1,score:1},{round:1,rank:2,score:0}]});
  assert.match(ranked,/Recommended Patch: Patch 2/); assert.match(ranked,/Score 1/); assert.match(ranked,/does not establish correctness or security/);
});

test('research demo renders real inference and clearly labels synthetic data', async () => {
  const root = resolve(process.cwd(), '..');
  const python = resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const result = JSON.parse(execFileSync(python, ['-c', 'import json; from backend.app.ranker_demo import research_demo; print(json.dumps(research_demo()))'], { cwd: root, encoding: 'utf8' }));
  const { RankerDemoView } = await server.ssrLoadModule('/src/ranker-demo.jsx');
  const markup = renderToStaticMarkup(React.createElement(RankerDemoView, { result }));
  assert.match(markup, /Model prefers Patch A/); assert.match(markup, /synthetic training data/);
  assert.match(markup, /not been independently validated/); assert.match(markup, /Tests were not run and no patch was applied/);
  assert.match(markup, /Uses int\(s\)/); assert.match(markup, /Uses eval\(s\)/);
  assert.match(markup, /no longer reports the original eval finding/); assert.match(markup, /still reports the original eval finding/);
  assert.match(markup, /How was this ranking calculated/);
  for (const item of result.candidates) { assert.ok(markup.includes(item.code.trim())); assert.ok(markup.includes(String(item.score))); }
  assert.match(renderToStaticMarkup(React.createElement(components.App, { initialPath: '/research/neural-ranking' })), /Neural Patch Ranking/);
});

test('failed second-round Python syntax preserves first proposal and explains ranking', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const review = { filename: 'a.py', original_code: 'x=1', bandit_before: [], review_status: 'complete', refinement_status: 'partial',
    refinement_failure: { category: 'invalid_python' }, neural_ranking: { status: 'single_candidate', candidates: [] },
    rounds: [{ round: 1, proposed_code: 'x=2', defender_explanation: 'First proposal.', challenger_feedback: 'Review input.', suggested_tests: [] }] };
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1, setRound: noop } }));
  assert.match(markup,/Partially complete/); assert.match(markup,/second version could not be validated/);
  assert.match(markup,/First proposal/); assert.match(markup,/Only one eligible patch/); assert.doesNotMatch(markup,/Rank 1: Patch 2/);
});

test('real mocked backend stream reaches result UI for one and two rounds', async () => {
  const root = resolve(process.cwd(), '..');
  const python = resolve(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  assert.ok(existsSync(python));
  const {AIResultsPage} = await server.ssrLoadModule('/src/simple-review.jsx');
  const previous = globalThis.fetch;
  try {
    for (const refine of [false,true]) {
      const output = execFileSync(python,['backend/tests/ranker_stream_fixture.py',...(refine ? ['refine'] : [])],{cwd:root,encoding:'utf8'});
      globalThis.fetch = async () => new Response(output,{status:200});
      const result = await streamReview({file:new File(['x=1'],'source.py'),consent:true,refine});
      const markup = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review:result,round:1,setRound:noop}}));
      assert.match(markup,/Neural Patch Ranker/);
      if (refine) {
        assert.equal(result.rounds.length,2); assert.equal(result.neural_ranking.status,'available');
        const winners = result.neural_ranking.candidates.filter(c => c.rank === 1);
        assert.ok(winners.length);
        if (winners.length === 1) assert.match(markup,new RegExp(`Recommended Patch: Patch ${winners[0].round}`));
        else { assert.match(markup,/Both patches received the same score/); assert.doesNotMatch(markup,/Recommended Patch: Patch/); }
        for (const candidate of result.neural_ranking.candidates) assert.ok(markup.includes(String(candidate.score)));
        const codePage = round => renderToStaticMarkup(React.createElement(components.CodeReview,{review:result,selectedRound:round,setSelectedRound:noop}));
        const first = codePage(1), second = codePage(2);
        assert.match(first,/Round 2/); assert.match(first,/Proposed code/); assert.match(first,/x = 2/);
        assert.match(second,/x = 3/); assert.doesNotMatch(second,/x = 2/);
      } else {
        assert.equal(result.rounds.length,1); assert.equal(result.neural_ranking.status,'single_candidate'); assert.match(markup,/Only one eligible patch/);
      }
      assert.match(markup,/does not establish correctness or security/);
    }
  } finally {globalThis.fetch = previous;}
});

test('candidate exclusion reasons are visible on results and code review', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const rounds = [{ round: 1, proposed_code: 'x=2', defender_explanation: 'Change.', challenger_feedback: 'Review.',
    candidate_assessment: { reasons: ['possible_unrelated_change'] }, verification: {} }];
  const review = { filename: 'a.py', original_code: 'x=1', rounds, neural_ranking: { status: 'no_valid_candidates', candidates: [] } };
  const results = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1, setRound: noop } }));
  const code = renderToStaticMarkup(React.createElement(components.CodeReview, { review, selectedRound: 1, setSelectedRound: noop }));
  for (const page of [results, code]) assert.match(page, /Changes outside the targeted statement require review/);
});

test('ranking inspection selects the requested round and ties do not claim a unique preference', async () => {
  const { NeuralRanking } = await server.ssrLoadModule('/src/simple-review.jsx');
  const ranking = { status: 'available', candidates: [{ round: 1, rank: 1, score: 0.5 }, { round: 2, rank: 1, score: 0.5 }] };
  const rounds = [{ round: 1, proposed_code: 'same' }, { round: 2, proposed_code: 'same' }];
  let selected = 0;
  const props = { ranking, rounds, setRound: value => { selected = value; } };
  const markup = renderToStaticMarkup(React.createElement(NeuralRanking, props));
  assert.match(markup, /Identical code/); assert.doesNotMatch(markup, /Model prefers/);
  const tree = NeuralRanking(props), links = [];
  const visit = node => {if(Array.isArray(node)) return node.forEach(visit); if(!node || typeof node !== 'object') return; if(node.props?.to === '/code-review') links.push(node); visit(node.props?.children);};
  visit(tree); assert.equal(links.length,2); links[1].props.onClick(); assert.equal(selected,2);
  assert.match(renderToStaticMarkup(React.createElement(NeuralRanking,{ranking:null,rounds,setRound:noop})),/Neural ranking unavailable/);
});

test('streaming review sends one consented ZIP request and consumes real events', async () => {
  const original = globalThis.fetch, calls = [], stages = [];
  const lines = [{ type: 'stage', stage: 'defender_started' }, { type: 'stage', stage: 'defender_completed' },
    { type: 'result', result: { review_status: 'complete', selected_file: 'src/a.py' } }].map(value => JSON.stringify(value)).join('\n') + '\n';
  globalThis.fetch = async (path, options) => { calls.push({ path, options }); return { ok: true,
    body: new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode(lines)); controller.close(); } }) }; };
  try {
    const result = await streamReview({ file: new File(['zip'], 'project.zip'), consent: true, member: 'src/a.py', refine: true, onEvent: stage => stages.push(stage) });
    assert.equal(calls.length, 1); assert.equal(calls[0].path, '/api/ai-review/stream');
    assert.equal(calls[0].options.body.get('member'), 'src/a.py');
    assert.deepEqual(calls[0].options.headers, { 'X-AI-Consent': 'true', 'X-AI-Refine': 'true' });
    assert.deepEqual(stages, ['defender_started', 'defender_completed']); assert.equal(result.selected_file, 'src/a.py');
  } finally { globalThis.fetch = original; }
});

test('scoped notebook selection is sent with explicit cell and finding', async () => {
  const original = globalThis.fetch;
  let options;
  globalThis.fetch = async (path, value) => { options = value; return { ok: true,
    text: async () => JSON.stringify({ type: 'result', result: { review_status: 'complete' } }) + '\n' }; };
  try {
    await streamReview({ file: new File(['synthetic'], 'project.zip'), consent: true, member: 'nested/demo.ipynb', cell: 2, findingLine: 5 });
    assert.equal(options.body.get('member'), 'nested/demo.ipynb');
    assert.equal(options.body.get('cell'), '2');
    assert.equal(options.body.get('finding_line'), '5');
  } finally { globalThis.fetch = original; }
});

test('large source needs a selected finding and scoped comparison is labeled', () => {
  const props = { file: { name: 'big.py', size: 20000 }, scan: {}, selected: 'big.py', busy: '', consent: true,
    setConsent: noop, refine: false, setRefine: noop, runReview: noop };
  const initial = renderToStaticMarkup(React.createElement(components.ReviewSetup, props));
  assert.match(initial,/Select an eligible issue/); assert.match(initial,/disabled/);
  const selected = renderToStaticMarkup(React.createElement(components.ReviewSetup,{...props,selectedLine:12})); assert.match(selected,/line 12/);
  const review={filename:'big.py',scope:{kind:'finding',start_line:8,end_line:16,finding_line:12},original_code:'x=1',bandit_before:[],rounds:[{round:1,proposed_code:'x=2',bandit_after:[]}]};
  const comparison=renderToStaticMarkup(React.createElement(components.CodeReview,{review,selectedRound:1,setSelectedRound:noop}));
  assert.match(comparison,/Reviewed code section only/); assert.match(comparison,/x=1/); assert.match(comparison,/x=2/);
});

test('streaming fallback and error never trigger a second request', async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return { ok: true, text: async () => JSON.stringify({ type: 'error', category: 'truncated_response', message: 'Response was truncated.' }) + '\n' }; };
  try {
    await assert.rejects(streamReview({ file: new File(['x'], 'source.py'), consent: true }), error => error.category === 'truncated_response');
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('malformed and incomplete review streams report their actual failure type', async () => {
  const original = globalThis.fetch;
  try {
    for (const [body, category] of [['not json\n', 'invalid_review_stream'], ['{"type":"stage","stage":"defender_started"}\n', 'incomplete_review_stream']]) {
      globalThis.fetch = async () => ({ok:true,text:async()=>body});
      await assert.rejects(streamReview({file:new File(['x'],'source.py'),consent:true}), error => error.category === category);
    }
  } finally { globalThis.fetch = original; }
});

test('a direct progress-page visit without a running request does not start a review', () => {
  const markup = renderToStaticMarkup(React.createElement(components.App, { initialPath: '/ai-review/progress' }));
  assert.match(markup, /No review in progress/);
  assert.match(markup, /Your uploaded file is no longer available/);
  assert.match(markup, /href="\/scan"/);
});

test('stream disconnect preserves reported stages and never retries automatically', async () => {
  const original = globalThis.fetch, stages = [];
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return { ok: true, body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"type":"stage","stage":"defender_started"}\n'));
        setTimeout(() => controller.error(new Error('synthetic disconnect')), 0);
      },
    }) };
  };
  try {
    await assert.rejects(streamReview({ file: new File(['synthetic'], 'source.py'), consent: true, onEvent: stage => stages.push(stage) }), /synthetic disconnect/);
    assert.deepEqual(stages, ['defender_started']);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('line diff preserves both sources and assigns line numbers for edits and duplicates', () => {
  for (const [oldSource, newSource] of [
    ['a\nb\nc\n', 'a\nx\nc\n'],
    ['same\nsame\nend', 'same\nnew\nsame\nend'],
    ['', 'new'], ['old', ''], ['a\n', 'a'],
  ]) {
    const result = lineDiff(oldSource, newSource);
    assert.equal(result.operations.filter(item => item.type !== 'add').map(item => item.text).join('\n'), oldSource);
    assert.equal(result.operations.filter(item => item.type !== 'remove').map(item => item.text).join('\n'), newSource);
    assert.equal(result.coarse, false);
  }
  const diff = lineDiff('a\nb\nc', 'a\nx\nc');
  assert.deepEqual(diff.operations.map(item => item.type), ['equal', 'remove', 'add', 'equal']);
  const rows = splitDiffRows(diff.operations);
  assert.equal(rows[1].left.oldLine, 2);
  assert.equal(rows[1].right.newLine, 2);
  assert.equal(rows[2].left.oldLine, 3);
});

test('line diff aligns insertions, removals, repeated lines, reordering and unchanged files', () => {
  const cases = [
    ['a\nb\nc', 'import x\na\nb\nc\nend'],
    ['import x\na\nb\nc\nend', 'a\nb\nc'],
    ['a\nsame\nsame\nb', 'a\nsame\nadded\nsame\nb'],
    ['alpha\nbeta\ngamma', 'gamma\nalpha\nbeta'],
    ['unchanged\nfile\n', 'unchanged\nfile\n'],
  ];
  for (const [original, proposed] of cases) {
    const result = lineDiff(original, proposed);
    const oldOps = result.operations.filter(item => item.oldLine !== null);
    const newOps = result.operations.filter(item => item.newLine !== null);
    assert.equal(oldOps.map(item => item.oldText).join('\n'), original);
    assert.equal(newOps.map(item => item.newText).join('\n'), proposed);
    assert.deepEqual(oldOps.map(item => item.oldLine), oldOps.map((_, index) => index + 1));
    assert.deepEqual(newOps.map(item => item.newLine), newOps.map((_, index) => index + 1));
    assert.ok(result.operations.filter(item => item.type === 'equal').every(item => item.oldText === item.newText));
  }
  assert.ok(lineDiff(cases[4][0], cases[4][1]).operations.every(item => item.type === 'equal'));
  const moved = lineDiff(cases[3][0], cases[3][1]).operations;
  assert.ok(moved.some(item => item.type === 'remove') && moved.some(item => item.type === 'add'));
});

test('large files retain common and repeated lines between edits', () => {
  for (const lines of [Array.from({ length: 1200 }, (_, i) => `line ${i}`), Array(1200).fill('    pass')]) {
    const original = lines.join('\n');
    const proposed = ['import extra', ...lines, 'end'].join('\n');
    const result = lineDiff(original, proposed);
    assert.equal(result.coarse, false);
    assert.equal(result.operations.filter(item => item.type === 'equal').length, lines.length);
    assert.equal(result.operations.filter(item => item.type === 'add').length, 2);
    assert.equal(result.operations.filter(item => item.type === 'remove').length, 0);
    assert.equal(result.operations.find(item => item.type === 'equal').newLine, 2);
  }
});

test('repeated inserted lines do not misalign a large unchanged sequence', () => {
  const original = Array.from({ length: 1000 }, (_, index) => index % 2 ? 'B' : 'A');
  const proposed = [...Array(200).fill('A'), ...original, 'end'];
  const result = lineDiff(original.join('\n'), proposed.join('\n'));
  assert.equal(result.coarse, false);
  assert.equal(result.operations.filter(item => item.type === 'equal').length, 1000);
  assert.equal(result.operations.filter(item => item.type === 'add').length, 201);
  assert.equal(result.operations.filter(item => item.type === 'remove').length, 0);
  assert.equal(result.operations.filter(item => item.oldLine !== null).map(item => item.oldText).join('\n'), original.join('\n'));
  assert.equal(result.operations.filter(item => item.newLine !== null).map(item => item.newText).join('\n'), proposed.join('\n'));
});

test('bounded large-file comparison agrees with an independent LCS on repeated edits', () => {
  let seed = 42;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed; };
  const original = Array.from({ length: 720 }, () => `line ${random() % 11}`);
  const proposed = original.slice();
  for (let index = 0; index < 12; index++) {
    proposed.splice(random() % proposed.length, 1);
    proposed.splice(random() % (proposed.length + 1), 0, `line ${random() % 11}`);
  }
  let next = new Uint16Array(proposed.length + 1);
  for (let i = original.length - 1; i >= 0; i--) {
    const current = new Uint16Array(proposed.length + 1);
    for (let j = proposed.length - 1; j >= 0; j--) {
      current[j] = original[i] === proposed[j] ? next[j + 1] + 1 : Math.max(next[j], current[j + 1]);
    }
    next = current;
  }
  const result = lineDiff(original.join('\n'), proposed.join('\n'));
  assert.equal(result.coarse, false);
  assert.equal(result.operations.filter(item => item.type === 'equal').length, next[0]);
  assert.equal(result.operations.filter(item => item.oldLine !== null).map(item => item.oldText).join('\n'), original.join('\n'));
  assert.equal(result.operations.filter(item => item.newLine !== null).map(item => item.newText).join('\n'), proposed.join('\n'));
});

test('large anchor fallback is identified even when its individual gaps are small', () => {
  const original = Array.from({ length: 1000 }, (_, index) => `line ${index}`);
  const proposed = original.map((line, index) => index % 2 ? `replacement ${index}` : line);
  const result = lineDiff(original.join('\n'), proposed.join('\n'));
  assert.equal(result.coarse, true);
  assert.equal(result.operations.filter(item => item.type === 'equal').length, 500);
  assert.equal(result.operations.filter(item => item.oldLine !== null).map(item => item.oldText).join('\n'), original.join('\n'));
  assert.equal(result.operations.filter(item => item.newLine !== null).map(item => item.newText).join('\n'), proposed.join('\n'));
});

test('CRLF and LF match visibly while original text remains recoverable', () => {
  const original = 'import os\r\nprint(1)\r\n';
  const proposed = 'import os\nprint(1)\n';
  const result = lineDiff(original, proposed);
  assert.equal(result.lineEndingsDiffer, true);
  assert.ok(result.operations.every(item => item.type === 'equal'));
  assert.equal(result.operations.map(item => item.oldText).join('\n'), original);
  assert.equal(result.operations.map(item => item.newText).join('\n'), proposed);
  assert.equal(result.operations[0].text, 'import os');
});

test('large line comparisons use a bounded fallback and preserve both sources', () => {
  const oldSource = Array.from({ length: 750 }, (_, i) => `old ${i}`).join('\n');
  const newSource = Array.from({ length: 750 }, (_, i) => `new ${i}`).join('\n');
  const result = lineDiff(oldSource, newSource);
  assert.equal(result.coarse, true);
  assert.equal(result.operations.filter(item => item.type !== 'add').map(item => item.text).join('\n'), oldSource);
  assert.equal(result.operations.filter(item => item.type !== 'remove').map(item => item.text).join('\n'), newSource);
});



test('scan progress is immediate, indeterminate, accessible and retryable', () => {
  const active = renderToStaticMarkup(React.createElement(components.ScanProgress, { file: {name:'demo.zip'}, error:'', retry:noop, chooseAnother:noop }));
  assert.match(active, /Scanning your code/); assert.match(active, /demo.zip/);
  assert.match(active, /role="progressbar"/); assert.doesNotMatch(active, /aria-valuenow|[0-9]+%/);
  assert.match(active, /role="status"/);
  const measured = renderToStaticMarkup(React.createElement(components.ScanProgress, { file: {name:'demo.zip'}, progress:{stage:'upload',loaded:50,total:100}, error:'', retry:noop, chooseAnother:noop }));
  assert.match(measured, /50%/); assert.match(measured, /aria-valuenow="50"/); assert.match(measured, /Upload progress/);
  const pending = renderToStaticMarkup(React.createElement(components.ScanProgress, { file: {name:'demo.zip'}, progress:{stage:'processing'}, error:'', retry:noop, chooseAnother:noop }));
  assert.doesNotMatch(pending, /aria-valuenow|100%/); assert.match(pending, /Analysis progress is unavailable/);
  const complete = renderToStaticMarkup(React.createElement(components.ScanProgress, {file:{name:'demo.zip'}, progress:{stage:'complete'}, error:'', retry:noop, chooseAnother:noop}));
  assert.match(complete, /100%/); assert.match(complete, /Scan complete/);
  const failed = renderToStaticMarkup(React.createElement(components.ScanProgress, { file: {name:'demo.zip'}, error:'Network failed', retry:noop, chooseAnother:noop }));
  assert.match(failed, /role="alert"/); assert.match(failed, /Network failed/); assert.match(failed, /Retry scan/);
});

test('scan upload reports measured request bytes and preserves backend errors', async () => {
  const { requestScan } = await import('./src/api.js');
  const previous = globalThis.XMLHttpRequest, events = [];
  let xhr;
  class FakeXHR {
    constructor() { xhr = this; this.upload = {}; }
    open(method, path) { assert.equal(method, 'POST'); assert.equal(path, '/api/scan'); }
    send(form) { assert.ok(form.get('file')); }
    abort() { this.aborted = true; }
  }
  globalThis.XMLHttpRequest = FakeXHR;
  try {
    const request = requestScan('/api/scan', {file:new File(['x'], 'a.py'), onProgress: event => events.push(event)});
    xhr.upload.onprogress({lengthComputable:true,loaded:2,total:4}); xhr.upload.onload();
    assert.deepEqual(events, [{stage:'upload',loaded:2,total:4},{stage:'processing'}]);
    xhr.status=413; xhr.responseText=JSON.stringify({detail:'Upload too large.'}); xhr.onload();
    await assert.rejects(request, /Upload too large/);
  } finally { globalThis.XMLHttpRequest = previous; }
});

test('scan stream consumes measured analysis progress and requires a final result', async () => {
  const { requestScan } = await import('./src/api.js');
  const previous = globalThis.XMLHttpRequest, events = []; let xhr;
  class FakeXHR { constructor() { xhr = this; this.upload = {}; this.status = 200; this.responseText = ''; } open() {} send() {} }
  globalThis.XMLHttpRequest = FakeXHR;
  try {
    const pending = requestScan('/api/scan/stream', {file:new File(['x'], 'a.py'), onProgress:event=>events.push(event)});
    xhr.responseText = '{"type":"progress","completed":1,"total":2}\n'; xhr.onprogress();
    xhr.responseText += '{"type":"result","result":{"scan_status":"completed","findings":[]}}\n'; xhr.onload();
    assert.deepEqual(await pending, {scan_status:'completed',findings:[]});
    assert.deepEqual(events, [{stage:'analysis',completed:1,total:2},{stage:'complete'}]);
    const incomplete = requestScan('/api/scan/stream', {file:new File(['x'], 'a.py')});
    xhr.responseText = '{"type":"progress","completed":1,"total":2}\n'; xhr.onload();
    await assert.rejects(incomplete, /invalid or incomplete/);
    const partialEvents = [];
    const partial = requestScan('/api/scan/stream', {file:new File(['x'], 'a.py'), onProgress:event=>partialEvents.push(event)});
    xhr.responseText = '{"type":"result","result":{"scan_status":"partial","findings":[]}}\n'; xhr.onload();
    assert.equal((await partial).scan_status, 'partial'); assert.equal(partialEvents.some(event=>event.stage==='complete'), false);
  } finally { globalThis.XMLHttpRequest = previous; }
});

test('scan loader and ranking animations respect reduced motion', async () => {
  const { readFileSync } = await import('node:fs');
  const css = readFileSync(new URL('./src/style.css', import.meta.url), 'utf8');
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\{\.scan-progress-icon span,\.scan-indeterminate span,\.demo-score-track span\{animation:none\}/);
});

test('ranker demo handles negative scores, ties, invalid results and copies code', async () => {
  const { RankerDemoView, rankerComparison, copyCandidateCode } = await server.ssrLoadModule('/src/ranker-demo.jsx');
  const entries = [{label:'A', score:-3, rank:2, code:'a', syntax_valid:true, before_count:1, after_count:1, introduced_count:0}, {label:'B', score:-1, rank:1, code:'b', syntax_valid:true, before_count:1, after_count:0, introduced_count:0}];
  assert.deepEqual(rankerComparison(entries).winners, ['B']);
  const result = { candidates:entries, dataset_split:'train', requirement:'test', original_code:'x', model_version:'test' };
  const output = renderToStaticMarkup(React.createElement(RankerDemoView, {result}));
  assert.match(output, /Model prefers Patch B/); assert.match(output, /raw score -1/i);
  const tied = entries.map(candidate => ({...candidate, score:-1, rank:1}));
  assert.deepEqual(rankerComparison(tied).winners, ['A','B']);
  assert.match(renderToStaticMarkup(React.createElement(RankerDemoView, {result:{...result, candidates:tied}})), /ranked both patches equally/);
  assert.match(renderToStaticMarkup(React.createElement(RankerDemoView, {result:null})), /comparison is unavailable/);
  assert.deepEqual(rankerComparison([{...entries[0], score:NaN},entries[1]]).winners, []);
  assert.deepEqual(rankerComparison([{...entries[0], rank:1},entries[1]]).winners, []);
  const copied=[]; await copyCandidateCode(entries[0].code, {writeText:async text => copied.push(text)}); assert.deepEqual(copied,['a']);
});

test('review form separates findings, consent and optional second fix', () => {
  const props = {file:{name:'a.py',size:20},scan:{findings:[{line_number:1}]},selected:'a.py',selectedLine:1,busy:'',consent:false,setConsent:noop,refine:false,setRefine:noop,runReview:noop};
  const markup = renderToStaticMarkup(React.createElement(components.ReviewSetup, props));
  assert.match(markup,/Selected issue/); assert.match(markup,/Try a second fix/); assert.match(markup,/additional API calls/);
  assert.doesNotMatch(markup,/type="checkbox"[^>]*checked/); assert.match(markup,/disabled=""[^>]*>Start AI Review/);
  const checked=renderToStaticMarkup(React.createElement(components.ReviewSetup,{...props,consent:true,refine:true})); assert.equal((checked.match(/checked=""/g)||[]).length,2);
});


test('one scan request drives immediate loading, success navigation and explicit retry after failure', async () => {
  const guard = {current:null}, events = []; let calls = 0, resolveScan;
  const send = () => { calls++; return new Promise(resolve => { resolveScan = resolve; }); };
  const callbacks = {start:()=>events.push('loading'),success:()=>events.push('/results'),failure:e=>events.push(e.message),finish:()=>events.push('finished')};
  const first = components.executeScan({name:'a.py'}, guard, callbacks, send);
  assert.deepEqual(events, ['loading']);
  await components.executeScan({name:'a.py'}, guard, callbacks, send);
  assert.equal(calls, 1);
  resolveScan({findings:[]}); await first;
  assert.deepEqual(events, ['loading','/results','finished']);
  await components.executeScan({name:'a.py'}, guard, callbacks, async () => { throw new Error('Scan unavailable'); });
  assert.deepEqual(events.slice(-3), ['loading','Scan unavailable','finished']);
  assert.equal(guard.current, null);
});


test('review summary counts rounds and suggested tests independently', async () => {
  const {AIResultsPage} = await server.ssrLoadModule('/src/simple-review.jsx');
  const rounds = [1,2].map((round) => ({round, proposed_code:`x=${round}`, suggested_tests:round === 1 ? ['a','b'] : ['c'], bandit_after:[], verification:{syntax_valid:true}, candidate_assessment:{ranking_eligible:true,reasons:[]}}));
  const review = {filename:'a.py',original_code:'x=0',bandit_before:[{test_id:'B307'}],rounds,neural_ranking:{status:'available',candidates:[{round:2,rank:1,score:-1},{round:1,rank:2,score:-2}]}};
  const markup = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,round:1,setRound:noop}}));
  assert.match(markup,/AI review attempts: 2/); assert.match(markup,/Suggested tests: 2/); assert.match(markup,/Valid ranking candidates: 2/);
  assert.match(markup,/Recommended Patch: Patch 2/); assert.doesNotMatch(markup,/[0-9]+% secure/i);
});

test('code review labels full source availability and counts actual line edits', () => {
  const review = {filename:'a.py',original_code:'x=1\n',scope:{kind:'finding',start_line:1,end_line:1,finding_line:1},rounds:[{round:1,proposed_code:'x=2\n',verification:{target_rule_still_reported:true}}]};
  const render = value => renderToStaticMarkup(React.createElement(components.CodeReview,{review:value,selectedRound:1,setSelectedRound:noop}));
  const scoped=render(review); assert.match(scoped,/Full source preview is unavailable/); assert.match(scoped,/1 line removed, 1 line added/);
  assert.match(scoped,/still reported/); assert.match(scoped,/Copy Original/); assert.match(scoped,/Copy Proposed Code/);
  const full=render({...review,full_original_code:'import os\nx=1\n',rounds:[{...review.rounds[0],full_proposed_code:'import os\nx=2\n'}]});
  assert.match(full,/Full Source View/); assert.match(full,/Complete selected Python file/);
});

test('no eligible patch explains ranking unavailability', async () => {
  const {NeuralRanking} = await server.ssrLoadModule('/src/simple-review.jsx');
  const rounds = [{round:1,proposed_code:'x',candidate_assessment:{reasons:['invalid_or_unchecked_syntax']}}];
  const markup = renderToStaticMarkup(React.createElement(NeuralRanking,{ranking:{status:'no_valid_candidates'},rounds,setRound:noop}));
  assert.match(markup,/No valid patches available for ranking/); assert.match(markup,/Python syntax is invalid or was not checked/);
});


test('copy keeps original and proposed source unchanged', async () => {
  const {copySource} = await server.ssrLoadModule('/src/workspace-components.jsx');
  const copied = [], clipboard = {writeText: async text => copied.push(text)};
  const original = 'import os\r\nprint(1)\r\n', proposal = 'import os\nprint(2)\n';
  await copySource(original, clipboard); await copySource(proposal, clipboard);
  assert.deepEqual(copied, [original, proposal]);
});


test('unchanged review attempts do not count as fixes and another issue is primary', async () => {
  const {AIResultsPage} = await server.ssrLoadModule('/src/simple-review.jsx');
  const original = 'import subprocess\nsubprocess.run([])\n';
  const rounds = [1,2].map(round => ({round,proposed_code:original,bandit_after:[{test_id:'B404'}],suggested_tests:[],candidate_assessment:{ranking_eligible:false,reasons:['unchanged_from_original']}}));
  const review = {filename:'a.py', original_code:original,bandit_before:[{test_id:'B404'}], rounds, neural_ranking:{status:'no_valid_candidates'}};
  const scan = {findings:[{test_id:'B404',line_number:1},{test_id:'B307',line_number:5}]};
  const html = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,scan,round:1,setRound:noop}}));
  assert.match(html,/No new patch generated/); assert.match(html,/AI review attempts: 2/);
  assert.match(html,/Changed proposals: 0/); assert.match(html,/Valid ranking candidates: 0/); assert.match(html,/Compare Changes/);
});

test('findings can be selected independently including same-line rules and notebook cells', async () => {
  const {ScanReport, findingSelection} = await server.ssrLoadModule('/src/scan-report.jsx');
  const findings = [{file_path:'n.ipynb',cell_index:1,line_number:3,test_id:'B404'}, {file_path:'n.ipynb',cell_index:1,line_number:3,test_id:'B307'}];
  const scan = {filename:'project.zip',scan_status:'completed',findings,total_findings:2,findings_by_file:{'cell':findings},review_targets:{'cell':{path:'n.ipynb',cell_index:1}}};
  assert.deepEqual(findingSelection(scan,{name:'project.zip'},findings[1]), {source:'cell',line:3,rule:'B307'});
  const {IssueRow} = await server.ssrLoadModule('/src/scan-report.jsx');
  const calls=[], tree = IssueRow({item:findings[1],scan,file:{name:'project.zip'},onReview:(...args)=>calls.push(args)});
  const visit = node => {if(Array.isArray(node))return node.forEach(visit); if(!node||typeof node!=='object')return; if(node.type==='button')node.props.onClick();visit(node.props?.children);};
  visit(tree); assert.deepEqual(calls,[['cell',3,'B307']]);
});

test('review request includes selected Bandit rule', async () => {
  const prior=globalThis.fetch; let payload;
  globalThis.fetch=async (_,options)=>{payload=options.body;return new Response(JSON.stringify({type:'result',result:{ok:true}})+'\n');};
  try { await streamReview({file:new File(['x'], 'source.py'),consent:true,findingLine:9,findingId:'B404'}); assert.equal(payload.get('finding_line'),'9'); assert.equal(payload.get('finding_id'),'B404'); } finally {globalThis.fetch=prior;}
});


test('multipart review sends exactly one named file with correct selection for all formats', async () => {
  const prior = globalThis.fetch;
  const cases = [
    {name:'source.py', text:'x=1', args:{findingLine:2,findingId:'B311'}},
    {name:'Vitiligo.ipynb', text:'{}', args:{cell:13,findingLine:18,findingId:'B311'}},
    {name:'project.zip', text:'zip', args:{member:'nested/demo.ipynb',cell:13,findingLine:18,findingId:'B311'}}
  ];
  try {
    for (const item of cases) {
      let requestOptions, decoded;
      globalThis.fetch = async (url,options) => { requestOptions=options; decoded=await new Request('http://localhost'+url,options).formData(); return new Response(JSON.stringify({type:'result',result:{ok:true}})+'\n'); };
      const file = new File([item.text], item.name);
      await streamReview({file,consent:true,...item.args});
      assert.equal(decoded.getAll('file').length,1); assert.equal(decoded.get('file').name,item.name);
      assert.equal(await decoded.get('file').text(),item.text);
      for (const [key,val] of Object.entries(item.args)) { const fields={findingLine:'finding_line', findingId:'finding_id'}; assert.equal(decoded.get(fields[key] || key),String(val)); }
      assert.equal(requestOptions.headers['X-AI-Consent'],'true');
      assert.equal(Object.keys(requestOptions.headers).some(key=>key.toLowerCase()==='content-type'),false);
    }
  } finally {globalThis.fetch=prior;}
});

test('missing file and absent consent prevent network requests', async () => {
  const prior=globalThis.fetch; let calls=0; globalThis.fetch=async()=>{calls++; throw new Error('must not send');};
  try {
    await assert.rejects(streamReview({file:null,consent:true}), /Your uploaded file is no longer available/);
    await assert.rejects(streamReview({file:new Blob(['x']),consent:true}), /Your uploaded file is no longer available/);
    await assert.rejects(streamReview({file:new File(['x'],'source.py')}), /Consent is required/);
    assert.equal(calls,0);
    const missing=renderToStaticMarkup(React.createElement(components.AIPage,{state:{scan:{},file:null}}));
    assert.match(missing,/Your uploaded file is no longer available/); assert.match(missing,/href="\/scan"/);
  } finally {globalThis.fetch=prior;}
});

test('old backend rejection and provider failure have distinct messages', async () => {
  const prior=globalThis.fetch;
  try {
    globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Provide one file in the file field.'}),{status:400});
    await assert.rejects(streamReview({file:new File(['x'],'source.py'),consent:true}), error => error.category==='request_error' && /Restart the backend/.test(error.message));
    globalThis.fetch=async()=>new Response(JSON.stringify({type:'error',category:'authentication',message:'Provider rejected access'})+'\n');
    await assert.rejects(streamReview({file:new File(['x'],'source.py'),consent:true}), error => error.category==='authentication');
  } finally {globalThis.fetch=prior;}
});


test('explicit retry sends one retained file and the same selected notebook finding', async () => {
  const prior=globalThis.fetch, payloads=[];
  globalThis.fetch=async (url,options)=>{
    payloads.push(await new Request('http://localhost'+url,options).formData());
    return new Response(JSON.stringify(payloads.length === 1 ? {type:'error',category:'transport_error',message:'Offline'} : {type:'result',result:{ok:true}})+'\n');
  };
  const file=new File(['notebook'],'Vitiligo.ipynb');
  const selection={file,consent:true,cell:13,findingLine:18,findingId:'B311'};
  try {
    await assert.rejects(streamReview(selection), error=>error.category==='transport_error');
    assert.equal(payloads.length,1);
    await streamReview(selection);
    assert.equal(payloads.length,2);
    for (const form of payloads) {
      assert.equal(form.getAll('file').length,1); assert.equal(form.get('file').name,'Vitiligo.ipynb');
      assert.equal(form.get('cell'),'13'); assert.equal(form.get('finding_line'),'18'); assert.equal(form.get('finding_id'),'B311');
    }
  } finally {globalThis.fetch=prior;}
});


test('research demo keeps technical details collapsed and stacks candidates on mobile', async () => {
  const {readFileSync} = await import('node:fs');
  const {RankerDemoView} = await server.ssrLoadModule('/src/ranker-demo.jsx');
  const result = {example_id:'x',dataset_split:'train',model_version:'model',candidates:[{label:'A',score:1,rank:1,code:'x=1'},{label:'B',score:0,rank:2,code:'x=2'}]};
  const html = renderToStaticMarkup(React.createElement(RankerDemoView,{result}));
  assert.match(html, /<details class="demo-technical"><summary>How was this ranking calculated/);
  assert.match(html, /Copy code/);
  const css = readFileSync(new URL('./src/style.css', import.meta.url),'utf8');
  assert.match(css, /\.demo-simple-grid\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /@media\(max-width:720px\)\{\.demo-simple-grid\{grid-template-columns:1fr\}/);
});


test('risk dashboard categorizes actual Bandit IDs without overlapping risk groups', async () => {
  const {categorizeFindings, RISK_GROUPS, ScanReport} = await server.ssrLoadModule('/src/scan-report.jsx');
  const rules = RISK_GROUPS.flatMap(group => group.rules);
  assert.equal(new Set(rules).size, rules.length);
  const ids = ['B404','B602','B608','B307','B105','B324','B999'];
  const findings = ids.map((test_id,index) => ({test_id, severity:index < 2 ? 'HIGH' : 'LOW', line_number:index+1}));
  assert.deepEqual(categorizeFindings(findings), {input:2,system:2,secrets:2,other:1,high:2});
  const scan = {filename:'source.py',scan_status:'completed',total_findings:7,findings};
  const html = renderToStaticMarkup(React.createElement(ScanReport,{scan,file:{name:'source.py'},onReview:noop}));
  assert.match(html,/aria-valuenow="28.6" aria-valuetext="2 of 7 findings"/); assert.match(html,/1 finding uses an unlisted rule/);
  assert.match(html,/Runtime errors and code quality · Not assessed/);
});

test('zero and partial findings avoid fabricated percentages and preserve skip details', async () => {
  const {ScanReport} = await server.ssrLoadModule('/src/scan-report.jsx');
  const scan = {filename:'n.ipynb',scan_type:'notebook',scan_status:'partial',analyzed_cells:0,findings:[],total_findings:0,skipped:[{path:'n.ipynb',cell_index:2,reason:'Cell could not be analyzed.'}]};
  const html = renderToStaticMarkup(React.createElement(ScanReport,{scan,file:{name:'n.ipynb'},onReview:noop}));
  assert.match(html,/No supported code was analyzed/); assert.match(html,/Not assessed/);
  assert.match(html,/code cell 3/); assert.match(html,/Cell could not be analyzed/);
  assert.doesNotMatch(html,/role="progressbar"/);
});

test('finding row shows fallback details, location and invokes the correct review', async () => {
  const {IssueRow} = await server.ssrLoadModule('/src/scan-report.jsx');
  const calls=[]; const item={test_id:'B602',line_number:19,description:'Check the command',file_path:'a/very-long/path/script.py'};
  const scan={filename:'p.zip',findings_by_file:{'script':[]},review_targets:{script:{path:item.file_path,cell_index:null}}};
  const props={item,scan,file:{name:'p.zip'},onReview:(...args)=>calls.push(args),busy:false};
  const html=renderToStaticMarkup(React.createElement(IssueRow,props));
  assert.match(html,/Unknown severity/); assert.match(html,/Confidence: not reported/);
  assert.match(html,/a\/very-long\/path\/script.py - line 19/); assert.match(html,/Check the command/);
  const tree=IssueRow(props); const visit=node=>{if(Array.isArray(node))return node.forEach(visit);if(!node||typeof node!=='object')return;if(node.type==='button')node.props.onClick();visit(node.props?.children);};
  visit(tree); assert.deepEqual(calls,[['script',19,'B602']]);
});

test('scan dashboard stacks on mobile and honors reduced motion', async () => {
  const {readFileSync} = await import('node:fs');
  const css=readFileSync(new URL('./src/style.css',import.meta.url),'utf8');
  assert.match(css, /\.scan-results-actions \{ flex-direction: column/);
  assert.match(css, /\.scan-report \.issue-row\{grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css, /\.scan-report \.issue-action \.button\{width:100%\}/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)\{\.scan-report \.measured-track>span\{animation:none\}/);
});

test('presentation shows validated full file and preserves round one on validation failure', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const round = {round:1, proposed_code:'x=2\n', full_proposed_code:'import os\nx=2\n', defender_explanation:'Change value.', challenger_feedback:'Check behavior.', suggested_tests:['test'], verification:{syntax_valid:true}};
  const review = {filename:'a.py', original_code:'x=1\n', full_original_code:'import os\nx=1\n', scope:{kind:'finding',start_line:2,end_line:2}, rounds:[round], refinement_status:'partial', refinement_failure:{category:'invalid_python'}, neural_ranking:{status:'single_candidate'}};
  const result = renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,round:1,setRound:noop}}));
  assert.match(result,/Patch 1 is ready/); assert.match(result,/second version could not be validated/);
  assert.match(result,/Only one eligible patch/); assert.match(result,/Compare Changes/);
  assert.match(result,/<summary>Technical details<\/summary>/);
  const code = renderToStaticMarkup(React.createElement(components.CodeReview,{review,selectedRound:1,setSelectedRound:noop}));
  assert.match(code,/Original code/); assert.match(code,/Proposed code/);
  assert.match(code,/Complete selected Python file/); assert.match(code,/x=1/); assert.match(code,/x=2/);
});

test('final review: readable findings and dynamic severity and type proportions', async () => {
  const {ScanReport, issueName} = await server.ssrLoadModule('/src/scan-report.jsx');
  assert.equal(issueName({test_id:'B404'}), 'Subprocess security warning');
  assert.equal(issueName({test_id:'B999'}), 'Security finding');
  const ids = ['B307','B608','B404','B602','B105','B324'];
  const findings = ids.map((test_id,i) => ({test_id,line_number:i+1,severity:i<3?'HIGH':i<5?'MEDIUM':'LOW',description:'Finding'}));
  const html = renderToStaticMarkup(React.createElement(ScanReport,{scan:{filename:'a.py',scan_status:'completed',total_findings:6,findings},file:{name:'a.py'},onReview:noop}));
  assert.match(html,/<span>High<\/span><strong>3<\/strong>/); assert.match(html,/<span>Medium<\/span><strong>2<\/strong>/); assert.match(html,/<span>Low<\/span><strong>1<\/strong>/);
  assert.equal((html.match(/aria-valuenow="33.3" aria-valuetext="2 of 6 findings"/g) || []).length, 3);
  assert.match(html,/<summary>Technical details<\/summary>/);
});

test('final review: scoped viewer fallback and static comparison are honest', async () => {
  const {staticOutcome} = await server.ssrLoadModule('/src/workspace-components.jsx');
  const review = {filename:'a.py',scope:{kind:'finding',start_line:2,end_line:2},original_code:'x=1\n',bandit_before:[{}],rounds:[{round:1,proposed_code:'x=2\n',bandit_after:[{}],verification:{target_rule_still_reported:false,remaining_findings:[],introduced_findings:[{}]}}]};
  const html = renderToStaticMarkup(React.createElement(components.CodeReview,{review,selectedRound:1,setSelectedRound:noop}));
  assert.match(html,/Original code/); assert.match(html,/Proposed code/); assert.match(html,/x=1/); assert.match(html,/x=2/);
  assert.match(html,/Copy Original/); assert.match(html,/Copy Proposed Code/); assert.match(html,/Select original file again/);
  assert.match(staticOutcome(review.bandit_before,review.rounds[0].bandit_after,review.rounds[0].verification),/another issue appeared/);
});

test('code review ranking validates real scores, ties, eligibility and missing data', async () => {
  const {reviewRanking} = await server.ssrLoadModule('/src/workspace-components.jsx');
  const rounds = [{round:1,proposed_code:'x=1'}, {round:2,proposed_code:'x=2'}];
  const rank = candidates => reviewRanking({status:'available',candidates},rounds);
  const first = rank([{round:1,rank:1,score:0},{round:2,rank:2,score:-2}]);
  assert.equal(first.winner,1); assert.deepEqual(first.candidates.map(item=>item.position),[1,0]);
  assert.equal(rank([{round:1,rank:2,score:-2},{round:2,rank:1,score:0}]).winner,2);
  assert.equal(rank([{round:1,rank:1,score:0},{round:2,rank:1,score:0}]).status,'tie');
  assert.equal(rank([{round:1,rank:1,score:NaN},{round:2,rank:2,score:0}]).status,'unavailable');
  assert.equal(reviewRanking({status:'single_candidate'},rounds).status,'single');
  assert.equal(reviewRanking({status:'no_valid_candidates'},rounds).status,'none');
  assert.equal(reviewRanking(null,rounds).status,'unavailable');
  assert.equal(reviewRanking({status:'available',candidates:[{round:1,rank:1,score:1},{round:2,rank:2,score:0}]},[rounds[0],{...rounds[1],candidate_assessment:{ranking_eligible:false}}]).status,'unavailable');
});

test('patch overview shows real rankings, actual proposal cards and working actions', async () => {
  const {PatchOverview} = await server.ssrLoadModule('/src/workspace-components.jsx');
  const rounds = [{round:1,proposed_code:'x=2',defender_explanation:'Change the value.',bandit_after:[],verification:{}},{round:2,proposed_code:'x=3',defender_explanation:'Use a different value.',bandit_after:[],verification:{}}];
  const scores = [{round:1,rank:2,score:-3},{round:2,rank:1,score:-1}];
  const review={original_code:'x=1',bandit_before:[],rounds,neural_ranking:{status:'available',candidates:scores}};
  const actions=[]; const props={review,onInspect:n=>actions.push(n),onCompare:()=>actions.push('compare')};
  const html=renderToStaticMarkup(React.createElement(PatchOverview,props));
  assert.match(html,/Recommended patch: <span>Patch 2/); assert.match(html,/Score -3/); assert.match(html,/Score -1/);
  assert.match(html,/Change the value/); assert.match(html,/Use a different value/); assert.doesNotMatch(html,/62%|88%/);
  assert.equal((html.match(/✓ Recommended/g)||[]).length,1);
  const visit=node=>{if(Array.isArray(node))return node.forEach(visit);if(!node||typeof node!=='object')return;if(node.type==='button')node.props.onClick();visit(node.props?.children);};
  visit(PatchOverview(props)); assert.deepEqual(actions,[1,2,'compare']);
  const first=renderToStaticMarkup(React.createElement(PatchOverview,{...props,review:{...review,neural_ranking:{status:'available',candidates:[{round:1,rank:1,score:0},{round:2,rank:2,score:-1}]}}})); assert.match(first,/Recommended patch: <span>Patch 1/);
  const tie=renderToStaticMarkup(React.createElement(PatchOverview,{...props,review:{...review,neural_ranking:{status:'available',candidates:scores.map(c=>({...c,rank:1,score:0}))}}})); assert.match(tie,/Both patches received the same score/); assert.doesNotMatch(tie,/✓ Recommended/);
  const single=renderToStaticMarkup(React.createElement(PatchOverview,{...props,review:{...review,rounds:[rounds[0]],refinement_status:'partial',neural_ranking:{status:'single_candidate'}}})); assert.match(single,/Only one eligible patch/); assert.doesNotMatch(single,/View Patch 2 code/); assert.match(single,/second review did not complete/);
  const none=renderToStaticMarkup(React.createElement(PatchOverview,{...props,review:{...review,neural_ranking:{status:'no_valid_candidates'}}})); assert.match(none,/No eligible fixes were generated/);
  const invalid=renderToStaticMarkup(React.createElement(PatchOverview,{...props,review:{...review,neural_ranking:{status:'available',candidates:[{round:1,rank:1,score:NaN},{round:2,rank:2,score:0}]}}})); assert.match(invalid,/ranking is unavailable/);
});

test('local full preview requires matching backend-validated hashes', async () => {
  const {restoreFullPreview}=await import('./src/api.js');
  const {webcrypto, createHash}=await import('node:crypto');
  const sha=text=>createHash('sha256').update(text).digest('hex');
  const original='import os\n\ndef run():\n    return 1\n\nprint(run())\n';
  const proposed='import os\n\ndef run():\n    return 2\n\nprint(run())\n';
  const file=new File([original],'large.py');
  const review={filename:'large.py',original_code:'def run():\n    return 1\n',scope:{kind:'finding',start_line:3,end_line:4},full_original_sha256:sha(original),rounds:[{round:1,proposed_code:'def run():\n    return 2\n',full_proposed_sha256:sha(proposed)}]};
  const restored=await restoreFullPreview(file,review,webcrypto);
  assert.equal(restored.full_original_code,original); assert.equal(restored.rounds[0].full_proposed_code,proposed);
  const mismatch=await restoreFullPreview(new File(['wrong'],'large.py'),review,webcrypto); assert.equal(mismatch,review);
  const tampered=await restoreFullPreview(file,{...review,rounds:[{...review.rounds[0],proposed_code:'bad code'}]},webcrypto); assert.equal(tampered.rounds[0].full_proposed_code,undefined);
  assert.equal(await restoreFullPreview(new File([original],'project.zip'),review,webcrypto),review);
});

test('AI results recommend the ranked patch and reject invalid rankings', async () => {
  const {AIResultsPage}=await server.ssrLoadModule('/src/simple-review.jsx');
  const review={filename:'a.py',original_code:'x=0',rounds:[{round:1,proposed_code:'x=1'},{round:2,proposed_code:'x=2'}],neural_ranking:{status:'available',candidates:[{round:1,rank:2,score:-2},{round:2,rank:1,score:0}]}};
  const render = ranking => renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review:{...review,neural_ranking:ranking},round:1,setRound:noop}}));
  const html=render(review.neural_ranking); assert.match(html,/result-recommendation/); assert.match(html,/Recommended Patch: Patch 2/); assert.match(html,/Score -2/); assert.match(html,/View Proposed Patch/);
  assert.match(html,/result-score is-preferred/); assert.match(html,/Patch 2 \(Recommended\)/);
  const tie=render({status:'available',candidates:[{round:1,rank:1,score:0},{round:2,rank:1,score:0}]}); assert.match(tie,/no unique recommendation/); assert.doesNotMatch(tie,/is-preferred|\(Recommended\)/);
  const invalid=render({status:'available',candidates:[{round:1,rank:1,score:NaN},{round:2,rank:2,score:0}]});
  assert.match(invalid,/Neural ranking is unavailable/); assert.doesNotMatch(invalid,/Recommended Patch: Patch/);
});

test('patch overview counts distinct changes and labels unchanged and duplicate rounds', async () => {
  const {PatchOverview} = await server.ssrLoadModule('/src/workspace-components.jsx');
  const render = proposal => renderToStaticMarkup(React.createElement(PatchOverview,{review:{original_code:'x=1',rounds:[{round:1,proposed_code:'x=2'},{round:2,proposed_code:proposal}],neural_ranking:{status:'single_candidate'}},onInspect:()=>{},onCompare:()=>{}}));
  const unchanged=render('x=1'); assert.match(unchanged,/Review rounds completed: 2/); assert.match(unchanged,/Distinct changed proposals: 1/); assert.match(unchanged,/Distinct eligible patches: 1/);
  assert.match(unchanged,/Code change proposed/); assert.match(unchanged,/No new patch generated/); assert.doesNotMatch(unchanged,/2 patch proposals available/);
  assert.match(unchanged,/View Round 2 code/); assert.doesNotMatch(unchanged,/View Patch 2 code|✓ Recommended/);
  const duplicate=render('x=2'); assert.match(duplicate,/Duplicate proposal/); assert.match(duplicate,/Distinct changed proposals: 1/);
});

test('review points omit list markers and duplicates and keep lengthy text in details', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const explanation = `1. Validate the input.\n2. Validate the input.\n- ${'Check the input carefully '.repeat(8)}for edge cases.\n3. Preserve the output.\n4. Keep this detail in the full review.`;
  const review = { original_code: 'x = 1', rounds: [{ round: 1, proposed_code: 'x = 2', defender_explanation: explanation }] };
  const html = renderToStaticMarkup(React.createElement(AIResultsPage, { state: { review, round: 1 } }));
  const cards = html.split('<details class="simple-technical"')[0];
  assert.match(cards, /<li>Validate the input\.<\/li>/);
  assert.match(cards, /…<\/li><li>Preserve the output\.<\/li>/);
  assert.doesNotMatch(cards, /for edge cases|Keep this detail/);
  assert.ok(html.includes(explanation));
});

test('partial zero-finding notebook shows compact coverage without invented bars', async () => {
  const {ScanReport}=await server.ssrLoadModule('/src/scan-report.jsx');
  const scan={filename:'Assignment_week5.ipynb',scan_type:'notebook',scan_status:'partial',analyzed_cells:106,findings:[],total_findings:0,findings_by_file:{},review_targets:{},skipped:[{path:'Assignment_week5.ipynb',cell_index:107,reason:'Cell could not be analyzed.'}]};
  const html=renderToStaticMarkup(React.createElement(ScanReport,{scan,file:{name:scan.filename},onReview:noop}));
  assert.match(html,/106 code cells analyzed/); assert.match(html,/Partial scan · 1 skipped item/);
  assert.match(html,/No security issues were reported in the code that was analyzed/); assert.match(html,/does not guarantee/);
  assert.match(html,/Cell could not be analyzed/); assert.match(html,/Not assessed/); assert.doesNotMatch(html,/role="progressbar"/);
});

test('exploratory results use the same real suggestions in summary and details without patch UI', async () => {
  const {AIResultsPage}=await server.ssrLoadModule('/src/simple-review.jsx');
  const review={filename:'Assignment_week5.ipynb',review_mode:'exploratory',review_status:'complete',scope:{kind:'cell',cell_index:1},rounds:[],exploratory_feedback:'The code reads input. Check input validation.',suggested_tests:['Try empty input','Try invalid input','Try normal input']};
  const html=renderToStaticMarkup(React.createElement(AIResultsPage,{state:{review,round:1,setRound:noop}}));
  assert.match(html,/Your code analysis/); assert.match(html,/Exploratory analysis complete/); assert.match(html,/3 suggested checks/);
  for(const item of review.suggested_tests) assert.equal(html.split(item).length-1,2);
  assert.match(html,/No patch was requested/); assert.match(html,/Neural Ranking Research Demo/); assert.doesNotMatch(html,/Defender|ranker-hero|None available|Model prefers Patch/);
});

test('result code actions select the ranked patch and the correct viewer target', async () => {
  const { AIResultsPage } = await server.ssrLoadModule('/src/simple-review.jsx');
  const rounds = [{round: 1, proposed_code: 'x=2'}, {round: 2, proposed_code: 'x=3'}];
  const review = {original_code: 'x=1', rounds, neural_ranking: {status: 'available', candidates: [{round: 1, rank: 2, score: 0}, {round: 2, rank: 1, score: 1}]}};
  let selected, target;
  const tree = AIResultsPage({state: {review, round: 1, setRound: value => { selected = value; }, setCodeTarget: value => { target = value; }}});
  const actions = [];
  const visit = node => { if (Array.isArray(node)) return node.forEach(visit); if (!node || typeof node !== 'object') return; if (node.props?.to === '/code-review') actions.push(node); visit(node.props?.children); };
  visit(tree);
  assert.equal(actions.length, 3);
  for (const [index, expected] of ['original', 'proposed', 'compare'].entries()) { actions[index].props.onClick(); assert.equal(selected, 2); assert.equal(target, expected); }
  const code = renderToStaticMarkup(React.createElement(components.CodeReview, {review, selectedRound: selected, setSelectedRound: noop}));
  assert.match(code, /id="code-original"/); assert.match(code, /id="code-proposed"/); assert.match(code, /x=1/); assert.match(code, /x=3/); assert.doesNotMatch(code, /x=2/);
});

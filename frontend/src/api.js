export function requestScan(path, { file, timeout = 150000, signal, onProgress = () => {} } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false, offset = 0, buffer = '', result = null, streamError = null, lastAnalysis = null;
    const finish = (error, result) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(result);
    };
    const abort = () => { xhr.abort(); finish(new Error('The scan was interrupted.')); };
    if (signal?.aborted) { finish(new Error('The scan was interrupted.')); return; }
    signal?.addEventListener('abort', abort, { once: true });
    xhr.open('POST', path);
    xhr.timeout = timeout;
    xhr.upload.onprogress = event => {
      if (event.lengthComputable && event.total > 0) {
        if (event.loaded >= event.total) onProgress({ stage: 'processing' });
        else onProgress({ stage: 'upload', loaded: event.loaded, total: event.total });
      }
    };
    xhr.upload.onload = () => onProgress({ stage: 'processing' });
    function consumeStream() {
      buffer += xhr.responseText.slice(offset); offset = xhr.responseText.length;
      let newline;
      while ((newline = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
        if (!line.trim()) continue;
        let event;
        try { event = JSON.parse(line); } catch { streamError = new Error('The scan response was invalid.'); return; }
        if (event.type === 'progress' && Number.isInteger(event.completed) && Number.isInteger(event.total) && event.total > 0 && event.completed >= 0 && event.completed <= event.total) { lastAnalysis = { completed: event.completed, total: event.total }; onProgress({ stage: 'analysis', ...lastAnalysis }); }
        else if (event.type === 'error') streamError = new Error(typeof event.message === 'string' ? event.message : 'Scan could not be completed.');
        else if (event.type === 'result') result = event.result;
      }
    }
    xhr.onprogress = () => { if (xhr.status >= 200 && xhr.status < 300) consumeStream(); };
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        let data; try { data = JSON.parse(xhr.responseText); } catch { data = null; }
        finish(new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${xhr.status}).`)); return;
      }
      consumeStream();
      if (streamError || buffer.trim() || !result || typeof result !== 'object' || Array.isArray(result)) { finish(streamError || new Error('The scan response was invalid or incomplete.')); return; }
      if (result.scan_status === 'completed') onProgress({ stage: 'complete', ...(lastAnalysis && lastAnalysis.completed === lastAnalysis.total ? lastAnalysis : {}) });
      finish(null, result);
    };
    xhr.onerror = () => finish(new Error('Cannot reach the backend. Check that FastAPI is running.'));
    xhr.ontimeout = () => finish(new Error('The request timed out. Please try again.'));
    const form = new FormData(); form.append('file', file); xhr.send(form);
  });
}

export async function request(path, { file, member, consent = false, refine = false, timeout = 10000, signal } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const options = { signal: controller.signal };
    if (file) {
      const form = new FormData();
      form.append('file', file);
      if (member) form.append('member', member);
      Object.assign(options, { method: 'POST', body: form, headers: { ...(consent ? { 'X-AI-Consent': 'true' } : {}), ...(refine ? { 'X-AI-Refine': 'true' } : {}) } });
    }
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. Please try again.');
    if (error instanceof TypeError) throw new Error('Cannot reach the backend. Check that FastAPI is running.');
    throw error;
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}

export const MISSING_REVIEW_FILE = 'Your uploaded file is no longer available. Please select it again to continue.';
export function hasReviewFile(file) {
  return typeof Blob !== 'undefined' && file instanceof Blob && typeof file.name === 'string' && file.name.length > 0;
}

// Rebuild only a locally retained .py file and accept it only when both hashes
// match the backend's already validated original and reconstructed Python.
export async function restoreFullPreview(file, review, cryptoApi = globalThis.crypto) {
  if (!hasReviewFile(file) || !/\.py$/i.test(file.name) || review?.selected_file || file.name !== review?.filename ||
      file.size > 8 * 1024 * 1024 || !cryptoApi?.subtle || !review.full_original_sha256) return review;
  try {
    const bytes = await file.arrayBuffer();
    const digest = async data => Array.from(new Uint8Array(await cryptoApi.subtle.digest('SHA-256', data)), b => b.toString(16).padStart(2, '0')).join('');
    if (await digest(bytes) !== review.full_original_sha256) return review;
    const original = new TextDecoder('utf-8', {fatal:true, ignoreBOM:true}).decode(bytes);
    const lines = original.match(/[^\n]*\n|[^\n]+$/g) || [];
    const start = review.scope?.start_line, end = review.scope?.end_line;
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > lines.length || lines.length > 100000) return review;
    const region = lines.slice(start - 1, end).join('');
    const indent = region.match(/^[ \t]*/)[0];
    const encoder = new TextEncoder();
    const rounds = await Promise.all((review.rounds || []).map(async round => {
      if (typeof round.proposed_code !== 'string' || !round.full_proposed_sha256) return round;
      let replacement = (round.proposed_code.match(/[^\n]*\n|[^\n]+$/g) || []).map(line => line.trim() ? indent + line : line).join('');
      if (/[\r\n]$/.test(region) && !/[\r\n]$/.test(replacement)) replacement += region.endsWith('\r\n') ? '\r\n' : '\n';
      const proposed = lines.slice(0, start - 1).join('') + replacement + lines.slice(end).join('');
      return await digest(encoder.encode(proposed)) === round.full_proposed_sha256 ? {...round, full_proposed_code:proposed} : round;
    }));
    return {...review, full_original_code:original, rounds};
  } catch { return review; }
}

// One POST owns the entire review. Never retry automatically if a stream fails.
export async function streamReview({ file, member, cell, findingLine, findingId, refine, signal, onEvent, consent = false }) {
  if (!consent) { const error = new Error('Consent is required before sending your code.'); error.category = 'request_error'; throw error; }
  if (!hasReviewFile(file)) { const error = new Error(MISSING_REVIEW_FILE); error.category = 'missing_file'; throw error; }
  const form = new FormData();
  form.append('file', file);
  if (member) form.append('member', member);
  if (cell !== null && cell !== undefined) form.append('cell', String(cell));
  if (findingLine !== null && findingLine !== undefined) form.append('finding_line', String(findingLine));
  if (findingId) form.append('finding_id', findingId);
  let response;
  try {
    response = await fetch('/api/ai-review/stream', { method: 'POST', body: form, signal,
      headers: { 'X-AI-Consent': 'true', ...(refine ? { 'X-AI-Refine': 'true' } : {}) } });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Cannot reach the backend. Check that FastAPI is running.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`;
    const error = new Error(response.status === 400 && message === 'Provide one file in the file field.' ? 'The backend rejected the upload fields. Restart the backend to load the current version, then retry.' : message);
    error.category = ({ 401: 'authentication', 402: 'billing', 403: 'authentication', 413: 'input_too_large', 415: 'unsupported_input', 429: 'rate_limit', 500: 'provider_http', 502: 'provider_http', 503: 'provider_http', 504: 'timeout' })[response.status] || 'request_error';
    throw error;
  }
  let buffer = '', result = null;
  function streamFailure(message, category) { const error = new Error(message); error.category = category; return error; }
  function consume(line) {
    if (!line.trim()) return;
    let event;
    try { event = JSON.parse(line); } catch { throw streamFailure('The review response was invalid.', 'invalid_review_stream'); }
    if (event.type === 'error') {
      const error = new Error(typeof event.message === 'string' ? event.message : 'The review could not be completed.');
      error.category = typeof event.category === 'string' ? event.category : 'request_error';
      throw error;
    }
    if (event.type === 'stage' && typeof event.stage === 'string') onEvent?.(event.stage);
    if (event.type === 'result' && event.result && typeof event.result === 'object') result = event.result;
  }
  function append(text) {
    buffer += text;
    if (buffer.length > 2 * 1024 * 1024) throw streamFailure('The review response exceeded the size limit.', 'review_stream_too_large');
    const lines = buffer.split('\n'); buffer = lines.pop(); lines.forEach(consume);
  }
  if (response.body?.getReader) {
    const reader = response.body.getReader(), decoder = new TextDecoder();
    try {
      while (true) { const { value, done } = await reader.read(); if (done) break; append(decoder.decode(value, { stream: true })); }
      append(decoder.decode());
    } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  } else {
    // A browser without a streaming reader remains indeterminate until completion.
    append(await response.text());
  }
  if (buffer.trim()) consume(buffer);
  if (!result) throw streamFailure('The review connection ended before a result was received.', 'incomplete_review_stream');
  return result;
}

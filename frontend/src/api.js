export async function request(path, { file, consent = false, timeout = 10000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const options = { signal: controller.signal };
    if (file) {
      const form = new FormData();
      form.append('file', file);
      Object.assign(options, { method: 'POST', body: form, headers: consent ? { 'X-AI-Consent': 'true' } : {} });
    }
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. Please try again.');
    if (error instanceof TypeError) throw new Error('Cannot reach the backend. Check that FastAPI is running.');
    throw error;
  } finally { clearTimeout(timer); }
}

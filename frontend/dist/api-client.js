/* SRW shared HTTP client (R4 slice 1).
 *
 * Behaviour is a byte-for-byte port of the `api()` helper that lived in app.js.
 * It is exposed as window.srwApi so that later feature modules can share one
 * request path instead of each re-implementing fetch, JSON parsing and error
 * extraction (which is what the convergence0*.js modules had to do).
 *
 * Two details are intentionally preserved, not "tidied":
 *
 * 1. `...opts` is spread AFTER `headers`, so a caller that passes its own
 *    `headers` replaces the merged object entirely. Callers that need the JSON
 *    content type must include it themselves. Changing this would alter requests
 *    for existing call sites.
 * 2. A non-2xx response throws `body.detail || body.error.code || String(body)`,
 *    so the UI keeps showing the server's detail text exactly as before.
 */
async function srwApi(path, opts = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  let body;
  const contentType = response.headers.get('content-type') || '';
  body = contentType.includes('json') ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.detail || body?.error?.code || String(body);
    throw new Error(message);
  }
  return body;
}

window.srwApi = srwApi;

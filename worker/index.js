// C7-2: the /api/* proxy of the finpo Worker (D2). Access has already checked the person
// before this runs; this adds the D1 signature so that Cloud Run can tell the request came
// through here, and never lets the browser see the secret.
//
// Canonical string, as web_auth.Auth.verify_request rebuilds it from the raw request line:
//   {unix seconds}|{METHOD}|{path+query}|{sha256(body) lowercase hex}

const encoder = new TextEncoder();

// Mirrors web_input.MAX_UPLOAD. Checked before hashing so an oversized body costs no CPU
// against the 10 ms Free-plan limit; the backend still enforces its own cap.
const MAX_UPLOAD = 5 * 1024 * 1024;

// Only what the backend reads. An allowlist keeps the Access cookie and assertion, and
// anything the browser adds, off the backend and out of its request log. A header the
// backend starts reading later must be added here, as C6-2's upload headers had to be.
const REQUEST_HEADERS = ['content-type', 'origin', 'x-portfolio-token', 'x-upload-filename', 'x-upload-sheet'];
const RESPONSE_HEADERS = ['content-type', 'content-disposition', 'cache-control', 'content-security-policy',
  'x-content-type-options', 'referrer-policy'];

function hex(buffer) {
  return [...new Uint8Array(buffer)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function sign(secret, timestamp, method, target, body) {
  const digest = hex(await crypto.subtle.digest('SHA-256', body));
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, encoder.encode(`${timestamp}|${method}|${target}|${digest}`)));
}

// Same shape as WebError.payload, so app.js shows the message instead of treating the
// reply as an Access redirect: it reloads the page on any text/html response.
function failure(status, code, message) {
  return Response.json({code, message, issues: []}, {status, headers: {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}});
}

function isApi(pathname) {
  return pathname === '/api' || pathname.startsWith('/api/');
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // run_worker_first sends only /api/* here, but a path with no static asset falls back
    // to the Worker too; nothing outside /api may reach the backend signed.
    if (!isApi(url.pathname)) return failure(404, 'invalid_input', '找不到頁面。');
    const secret = env.PROXY_HMAC_SECRET;
    if (!secret || encoder.encode(secret).length < 32 || !env.UPSTREAM_ORIGIN) {
      return failure(500, 'proxy_misconfigured', '代理設定不完整，請聯絡管理者。');
    }
    const declared = Number(request.headers.get('content-length') ?? 0);
    if (!(declared <= MAX_UPLOAD)) return failure(413, 'invalid_input', '檔案不得超過 5 MiB。');
    const bodyless = request.method === 'GET' || request.method === 'HEAD';
    // One buffer serves both the digest and the forwarded body (D2): hashing a re-encoded
    // copy would sign bytes the backend never receives.
    const body = bodyless ? new ArrayBuffer(0) : await request.arrayBuffer();
    if (body.byteLength > MAX_UPLOAD) return failure(413, 'invalid_input', '檔案不得超過 5 MiB。');

    // The signed target is read back from the URL object that is fetched, so it is exactly
    // the request line that goes on the wire, after the URL parser's own normalisation.
    const upstream = new URL(env.UPSTREAM_ORIGIN);
    upstream.pathname = url.pathname;
    upstream.search = url.search;
    const target = upstream.pathname + upstream.search;
    const timestamp = String(Math.floor(Date.now() / 1000));
    const headers = new Headers();
    for (const name of REQUEST_HEADERS) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    headers.set('X-Timestamp', timestamp);
    headers.set('X-Signature', await sign(secret, timestamp, request.method, target, body));

    let response;
    try {
      response = await fetch(upstream, {method: request.method, headers, body: bodyless ? undefined : body, redirect: 'manual'});
    } catch {
      return failure(502, 'upstream_unreachable', '無法連線到後端服務，請稍後重試。');
    }
    // The edge cuts a subrequest at 125 s and hands back a 524 instead of throwing (C7-2).
    if (response.status === 524) {
      return failure(504, 'upstream_timeout', '後端未在連線時限內回應；已完成的部分會保留。若剛才是在儲存或更新，請重新整理頁面確認結果。');
    }
    // The backend answers JSON on every error and never redirects, so an HTML page or a
    // redirect came from the platform in front of it, and must not reach app.js as one.
    const type = response.headers.get('content-type') ?? '';
    if ((response.status >= 300 && response.status < 400) || (response.status >= 400 && !type.startsWith('application/json'))) {
      return failure(response.status >= 400 ? response.status : 502, 'upstream_error', '後端服務暫時無法回應，請稍後重試。');
    }
    const forwarded = new Headers();
    for (const name of RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value !== null) forwarded.set(name, value);
    }
    return new Response(response.body, {status: response.status, headers: forwarded});
  },
};

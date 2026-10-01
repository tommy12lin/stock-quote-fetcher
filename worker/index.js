// C7-2: the /api/* proxy of the finpo Worker (D2). Access has already checked the person
// before this runs; this adds the D1 signature so that Cloud Run can tell the request came
// through here, and never lets the browser see the secret.
//
// Canonical string, as web_auth.Auth.verify_request rebuilds it from the raw request line:
//   {unix seconds}|{METHOD}|{path+query}|{sha256(body) lowercase hex}
//
// C7-8: the Worker signs only after verifying the Access JWT itself, so that Access being
// switched off, scoped to previews, or given too wide a policy does not open the backend.
import {createRemoteJWKSet, jwtVerify} from 'jose';

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

// The issuer is compared as an exact string, so the team domain must be a bare https origin.
function isOrigin(value) {
  return typeof value === 'string' && URL.canParse(value) && new URL(value).protocol === 'https:' && new URL(value).origin === value;
}

function allowedEmails(env) {
  return (env.ACCESS_ALLOWED_EMAILS ?? '').split(',').map(email => email.trim().toLowerCase()).filter(Boolean);
}

// jose's errors that say the token itself is bad. Anything else (the key set unreachable,
// timing out or malformed) is not the person's fault and is answered 503 instead.
const TOKEN_ERRORS = new Set(['ERR_JWT_EXPIRED', 'ERR_JWT_CLAIM_VALIDATION_FAILED', 'ERR_JWT_INVALID', 'ERR_JWS_INVALID',
  'ERR_JWS_SIGNATURE_VERIFICATION_FAILED', 'ERR_JOSE_ALG_NOT_ALLOWED', 'ERR_JOSE_NOT_SUPPORTED', 'ERR_JWKS_NO_MATCHING_KEY',
  'ERR_JWKS_MULTIPLE_MATCHING_KEYS']);

// One key set per isolate. jose's defaults keep the keys for 10 minutes and refetch on an
// unknown kid at most every 30 s, which picks up a rotation (every 6 weeks, per Cloudflare's
// docs; the old key stays valid for 7 days) without a deploy.
let keySet = null, keySetDomain = null;

// Reasons are logged by category only: never the token, never the email.
function refuse(reason) {
  console.log(JSON.stringify({access: 'denied', reason}));
  return failure(403, 'access_denied', '登入身分未通過驗證，請重新整理頁面；若仍無法使用，請聯絡管理者。');
}

// Only the header: Access adds it on each request it lets through, while the CF_Authorization
// cookie can outlive Access being switched off. Returns null when the request may be signed.
// The code is not 'unauthorized': app.js would take that for an expired session and retry.
async function denied(request, env, allowed) {
  const token = request.headers.get('cf-access-jwt-assertion');
  if (!token) return refuse('missing');
  if (keySetDomain !== env.ACCESS_TEAM_DOMAIN) {
    keySet = createRemoteJWKSet(new URL('/cdn-cgi/access/certs', env.ACCESS_TEAM_DOMAIN));
    keySetDomain = env.ACCESS_TEAM_DOMAIN;
  }
  let payload;
  try {
    ({payload} = await jwtVerify(token, keySet, {algorithms: ['RS256'], issuer: env.ACCESS_TEAM_DOMAIN,
      audience: env.ACCESS_AUD, requiredClaims: ['exp', 'email']}));
  } catch (error) {
    if (TOKEN_ERRORS.has(error?.code)) return refuse(error.claim ? `${error.code}:${error.claim}` : error.code);
    console.log(JSON.stringify({access: 'unverifiable', reason: error?.code ?? error?.name ?? 'unknown'}));
    return failure(503, 'access_unverifiable', '暫時無法確認登入狀態，請稍後重試。');
  }
  // A valid token from a too-wide Access policy still names someone not on this list.
  if (typeof payload.email !== 'string' || !allowed.includes(payload.email.trim().toLowerCase())) return refuse('email');
  return null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // run_worker_first sends only /api/* here, but a path with no static asset falls back
    // to the Worker too; nothing outside /api may reach the backend signed.
    if (!isApi(url.pathname)) return failure(404, 'invalid_input', '找不到頁面。');
    const secret = env.PROXY_HMAC_SECRET;
    const allowed = allowedEmails(env);
    if (!secret || encoder.encode(secret).length < 32 || !env.UPSTREAM_ORIGIN || !isOrigin(env.ACCESS_TEAM_DOMAIN)
      || !env.ACCESS_AUD || allowed.length === 0) {
      return failure(500, 'proxy_misconfigured', '代理設定不完整，請聯絡管理者。');
    }
    // Before the body is read, so a refused request costs no hashing.
    const refusal = await denied(request, env, allowed);
    if (refusal) return refusal;
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

// C7-2: the finpo Worker's /api/* proxy, run in Node with the upstream fetch replaced.
// The cross-language cases hand what the Worker actually sent to web_auth.Auth, the same
// code Cloud Run runs, so a drift on either side fails here rather than as a 401 in the cloud.
//
// C7-8: tokens are signed here by hand with WebCrypto, not with jose, so that the signing
// side and the verifying side do not share a defect. The key set is served by the same
// replaced fetch, at the path Access publishes it.
// Run `npm ci --prefix worker` first: the Worker imports jose from worker/node_modules.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import worker from '../worker/index.js';

const SECRET = 'c7-2-test-secret-that-is-at-least-32-bytes';
const UPSTREAM = 'https://stock-quote-896096883650.asia-northeast1.run.app';
const FRONT = 'https://finpo.drhiromu.workers.dev';
const TEAM = 'https://khlin.cloudflareaccess.com';
const AUD = 'c7-8-test-application-audience';
const OWNER = 'owner@example.test';
const env = {PROXY_HMAC_SECRET: SECRET, UPSTREAM_ORIGIN: UPSTREAM, ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, ACCESS_ALLOWED_EMAILS: OWNER};

async function signingKey(kid) {
  const pair = await crypto.subtle.generateKey({name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, true, ['sign', 'verify']);
  return {kid, privateKey: pair.privateKey, jwk: {...await crypto.subtle.exportKey('jwk', pair.publicKey), kid, alg: 'RS256', use: 'sig'}};
}
const KEY_A = await signingKey('key-a');
const KEY_B = await signingKey('key-b');
// Same kid as KEY_A, different key: a forgery that names a trusted key.
const IMPOSTOR = await signingKey('key-a');

const b64 = value => Buffer.from(typeof value === 'string' ? value : JSON.stringify(value)).toString('base64url');

// The claims Access puts in an application token; a claim given as undefined is left out.
async function mint(claims = {}, {key = KEY_A, header = {}} = {}) {
  const now = Math.floor(Date.now() / 1000);
  const input = `${b64({alg: 'RS256', kid: key.kid, typ: 'JWT', ...header})}.${b64({iss: TEAM, aud: [AUD], email: OWNER,
    iat: now, nbf: now, exp: now + 3600, type: 'app', ...claims})}`;
  const signature = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key.privateKey, Buffer.from(input));
  return `${input}.${Buffer.from(signature).toString('base64url')}`;
}

const publishing = keys => () => Response.json({keys: keys.map(key => key.jwk)});

// token: undefined mints a valid one, null sends none. keys answers the key set request.
async function proxy(request, reply = () => Response.json({ok: true}), environment = env, {token, keys = publishing([KEY_A])} = {}) {
  if (token !== null) {
    const headers = new Headers(request.headers);
    headers.set('Cf-Access-Jwt-Assertion', token ?? await mint());
    request = new Request(request, {headers});
  }
  const sent = [], fetched = [], logs = [];
  const original = globalThis.fetch, log = console.log;
  globalThis.fetch = async (url, init) => {
    const target = new URL(url);
    if (target.pathname === '/cdn-cgi/access/certs') {
      fetched.push(target.href);
      return keys();
    }
    sent.push({url: target, init, body: init.body === undefined ? new Uint8Array() : new Uint8Array(init.body)});
    return reply();
  };
  console.log = line => logs.push(JSON.parse(line));
  try {
    return {response: await worker.fetch(request, environment), sent, fetched, logs};
  } finally {
    globalThis.fetch = original;
    console.log = log;
  }
}

// Each case gets its own team domain, so the Worker's per-isolate key set starts empty.
let domains = 0;
function isolated(overrides = {}) {
  const team = `https://case-${++domains}.cloudflareaccess.com`;
  return {environment: {...env, ACCESS_TEAM_DOMAIN: team, ...overrides}, team};
}

// Rebuilds what uvicorn hands the Guard from the URL the Worker fetched: raw_path, and the
// query string without its '?'. Nothing here reuses the Worker's own signed string.
function verify(cases) {
  const script = `
import base64, json, sys
sys.path.insert(0, 'src')
from stock_quote_fetcher.web_auth import Auth
out = []
for c in json.load(sys.stdin):
    target = c['raw_path'].encode('ascii')
    if c['query_string']:
        target += b'?' + c['query_string'].encode('ascii')
    out.append(Auth(c['secret']).verify_request(c['timestamp'], c['method'], target, base64.b64decode(c['body']), c['signature']))
print(json.dumps(out))`;
  const result = spawnSync(process.env.PYTHON ?? 'python', ['-c', script], {input: JSON.stringify(cases), encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function received({url, init, body}, overrides = {}) {
  return {secret: SECRET, timestamp: init.headers.get('x-timestamp'), method: init.method, raw_path: url.pathname,
    query_string: url.search.slice(1), body: Buffer.from(body).toString('base64'), signature: init.headers.get('x-signature'), ...overrides};
}

test('Python accepts what the Worker signs, for GET, query, encoded path and binary upload', async () => {
  const upload = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0xff, 0x7c, 0x0a]);
  const requests = [
    new Request(FRONT + '/api/portfolio'),
    new Request(FRONT + '/api/portfolio/valuation?market=TW&x=%E4%B8%AD'),
    new Request(FRONT + '/api/jobs/中文 id'),
    new Request(FRONT + '/api/imports/preview', {method: 'POST', body: upload,
      headers: {'X-Upload-Filename': encodeURIComponent('持股.xlsx'), 'Origin': FRONT, 'X-Portfolio-Token': 't'}}),
    new Request(FRONT + '/api/portfolio', {method: 'PUT', body: '{"revision":5,"rows":[]}',
      headers: {'Content-Type': 'application/json', 'Origin': FRONT}}),
  ];
  const sent = [];
  for (const request of requests) sent.push(...(await proxy(request)).sent);
  assert.equal(sent.length, requests.length);
  assert.deepEqual(verify(sent.map(item => received(item))), requests.map(() => true));
  assert.deepEqual([...sent[3].body], [...upload]);
});

test('Python rejects the same requests once any signed field is altered', async () => {
  const {sent: [item]} = await proxy(new Request(FRONT + '/api/portfolio?market=TW', {method: 'PUT', body: '{"a":1}'}));
  assert.deepEqual(verify([
    received(item),
    received(item, {body: Buffer.from('{"a":2}').toString('base64')}),
    received(item, {raw_path: '/api/portfolio/valuation'}),
    received(item, {query_string: 'market=US'}),
    received(item, {method: 'POST'}),
    received(item, {secret: 'another-secret-that-is-also-32-bytes-long'}),
  ]), [true, false, false, false, false, false]);
});

test('only the headers the backend reads are forwarded', async () => {
  const {sent: [{init}]} = await proxy(new Request(FRONT + '/api/imports/preview', {method: 'POST', body: 'x', headers: {
    'Origin': FRONT, 'X-Portfolio-Token': 'token', 'X-Upload-Filename': 'a.xlsx', 'X-Upload-Sheet': 'S1',
    'Content-Type': 'application/octet-stream', 'Cookie': 'CF_Authorization=jwt', 'Cf-Access-Jwt-Assertion': 'jwt',
    'X-Forwarded-Host': 'evil.example', 'X-Timestamp': '1', 'X-Signature': 'f'.repeat(64)}}));
  assert.equal(init.headers.get('origin'), FRONT);
  assert.equal(init.headers.get('x-portfolio-token'), 'token');
  assert.equal(init.headers.get('x-upload-filename'), 'a.xlsx');
  assert.equal(init.headers.get('x-upload-sheet'), 'S1');
  assert.equal(init.headers.get('content-type'), 'application/octet-stream');
  for (const name of ['cookie', 'cf-access-jwt-assertion', 'x-forwarded-host']) assert.equal(init.headers.get(name), null, name);
  assert.notEqual(init.headers.get('x-timestamp'), '1');
  assert.notEqual(init.headers.get('x-signature'), 'f'.repeat(64));
  assert.equal(init.redirect, 'manual');
});

// '//evil.example/...' is also what would make a relative new URL(path, base) leave the
// upstream origin; this check is what keeps such a path from being signed at all.
test('paths outside /api are answered 404 without reaching the backend', async () => {
  for (const path of ['/', '/missing.js', '/apix', '//evil.example/api/x', '/api/../../x']) {
    const {response, sent} = await proxy(new Request(FRONT + path));
    assert.equal(response.status, 404, path);
    assert.equal(sent.length, 0, path);
  }
  const {sent} = await proxy(new Request(FRONT + '/api//evil.example/x'));
  assert.equal(sent[0].url.origin, UPSTREAM);
});

test('an oversized upload is refused before hashing or forwarding', async () => {
  const big = new Uint8Array(5 * 1024 * 1024 + 1);
  const {response, sent} = await proxy(new Request(FRONT + '/api/imports/preview', {method: 'POST', body: big}));
  assert.equal(response.status, 413);
  assert.equal(sent.length, 0);
  const exact = await proxy(new Request(FRONT + '/api/imports/preview', {method: 'POST', body: new Uint8Array(5 * 1024 * 1024)}));
  assert.equal(exact.sent.length, 1);
});

test('a missing or short secret fails closed without forwarding', async () => {
  for (const environment of [{UPSTREAM_ORIGIN: UPSTREAM}, {...env, PROXY_HMAC_SECRET: 'short'}, {PROXY_HMAC_SECRET: SECRET}]) {
    const {response, sent} = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment);
    assert.equal(response.status, 500);
    assert.equal(sent.length, 0);
  }
});

// The issuer is compared as an exact string, so a trailing slash or a path would refuse
// every real token; a plain-http domain would fetch the keys unprotected.
test('missing or malformed Access settings fail closed before any key set is fetched', async () => {
  const {ACCESS_AUD, ACCESS_ALLOWED_EMAILS, ACCESS_TEAM_DOMAIN, ...rest} = env;
  const environments = [
    {...rest, ACCESS_ALLOWED_EMAILS, ACCESS_TEAM_DOMAIN},
    {...rest, ACCESS_AUD, ACCESS_TEAM_DOMAIN},
    {...env, ACCESS_ALLOWED_EMAILS: ' , '},
    {...rest, ACCESS_AUD, ACCESS_ALLOWED_EMAILS},
    {...env, ACCESS_TEAM_DOMAIN: TEAM + '/'},
    {...env, ACCESS_TEAM_DOMAIN: TEAM + '/cdn-cgi/access/certs'},
    {...env, ACCESS_TEAM_DOMAIN: 'http://khlin.cloudflareaccess.com'},
  ];
  for (const [index, environment] of environments.entries()) {
    const {response, sent, fetched} = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment);
    assert.equal(response.status, 500, String(index));
    assert.equal((await response.json()).code, 'proxy_misconfigured', String(index));
    assert.deepEqual([sent.length, fetched.length], [0, 0], String(index));
  }
});

test('a request without an Access JWT is refused and never signed', async () => {
  for (const request of [new Request(FRONT + '/api/session'), new Request(FRONT + '/api/portfolio', {method: 'PUT', body: '{}'})]) {
    const {response, sent, logs} = await proxy(request, undefined, env, {token: null});
    assert.equal(response.status, 403);
    assert.match(response.headers.get('content-type'), /^application\/json/);
    assert.equal((await response.json()).code, 'access_denied');
    assert.equal(sent.length, 0);
    assert.deepEqual(logs, [{access: 'denied', reason: 'missing'}]);
  }
});

test('tokens that fail verification are refused without forwarding', async () => {
  const now = Math.floor(Date.now() / 1000);
  const valid = await mint();
  const [head, , signature] = valid.split('.');
  const cases = [
    ['signed by another key under a trusted kid', await mint({}, {key: IMPOSTOR}), 'ERR_JWS_SIGNATURE_VERIFICATION_FAILED'],
    ['payload swapped under a valid signature', `${head}.${b64({iss: TEAM, aud: [AUD], email: 'intruder@example.test', exp: now + 3600})}.${signature}`, 'ERR_JWS_SIGNATURE_VERIFICATION_FAILED'],
    ['another application', await mint({aud: ['another-application']}), 'ERR_JWT_CLAIM_VALIDATION_FAILED:aud'],
    ['another team', await mint({iss: 'https://other.cloudflareaccess.com'}), 'ERR_JWT_CLAIM_VALIDATION_FAILED:iss'],
    ['expired', await mint({exp: now - 10}), 'ERR_JWT_EXPIRED:exp'],
    ['not yet valid', await mint({nbf: now + 600}), 'ERR_JWT_CLAIM_VALIDATION_FAILED:nbf'],
    ['no expiry', await mint({exp: undefined}), 'ERR_JWT_CLAIM_VALIDATION_FAILED:exp'],
    ['no email', await mint({email: undefined}), 'ERR_JWT_CLAIM_VALIDATION_FAILED:email'],
    // What a too-wide Access policy would let through: a genuine token for someone else.
    ['someone not on the list', await mint({email: 'stranger@example.test'}), 'email'],
    ['an email that is not a string', await mint({email: [OWNER]}), 'email'],
    ['alg none', `${b64({alg: 'none', kid: KEY_A.kid})}.${valid.split('.')[1]}.`, 'ERR_JOSE_ALG_NOT_ALLOWED'],
    ['HS256 keyed with the public key', await (async () => {
      const input = `${b64({alg: 'HS256', kid: KEY_A.kid})}.${valid.split('.')[1]}`;
      const key = await crypto.subtle.importKey('raw', Buffer.from(KEY_A.jwk.n, 'base64url'), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
      return `${input}.${Buffer.from(await crypto.subtle.sign('HMAC', key, Buffer.from(input))).toString('base64url')}`;
    })(), 'ERR_JOSE_ALG_NOT_ALLOWED'],
    ['a kid the key set does not have', await mint({}, {key: KEY_B}), 'ERR_JWKS_NO_MATCHING_KEY'],
    ['not a JWT', 'not-a-jwt', 'ERR_JWS_INVALID'],
  ];
  for (const [name, token, reason] of cases) {
    const {response, sent, logs} = await proxy(new Request(FRONT + '/api/portfolio', {method: 'PUT', body: '{}'}), undefined, env, {token});
    assert.equal(response.status, 403, name);
    assert.equal((await response.json()).code, 'access_denied', name);
    assert.equal(sent.length, 0, name);
    assert.deepEqual(logs, [{access: 'denied', reason}], name);
  }
});

// Access adds this header in plain text; with Access off, anyone could send it.
test('the email comes from the signed token, not from the Access email header', async () => {
  const request = new Request(FRONT + '/api/portfolio', {headers: {'Cf-Access-Authenticated-User-Email': OWNER}});
  const {response, sent} = await proxy(request, undefined, env, {token: await mint({email: 'stranger@example.test'})});
  assert.equal(response.status, 403);
  assert.equal(sent.length, 0);
});

test('the email list ignores case and surrounding space, and admits every listed person', async () => {
  const environment = {...env, ACCESS_ALLOWED_EMAILS: ' Owner@Example.test , second@example.test '};
  for (const email of ['OWNER@example.TEST', 'second@example.test']) {
    const {response, sent} = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({email})});
    assert.equal(response.status, 200, email);
    assert.equal(sent.length, 1, email);
  }
});

// Not the person's fault, so not 403; and never a reason to sign.
test('an unreachable, failing or malformed key set fails closed with 503', async () => {
  const cases = [
    ['unreachable', () => { throw new TypeError('network'); }],
    ['server error', () => new Response('<html>502</html>', {status: 502, headers: {'content-type': 'text/html'}})],
    ['not JSON', () => new Response('<html>ok</html>', {headers: {'content-type': 'text/html'}})],
    ['not a key set', () => Response.json({keys: 'none'})],
  ];
  for (const [name, keys] of cases) {
    const {environment, team} = isolated();
    const {response, sent, fetched, logs} = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({iss: team}), keys});
    assert.equal(response.status, 503, name);
    assert.equal((await response.json()).code, 'access_unverifiable', name);
    assert.equal(sent.length, 0, name);
    assert.deepEqual(fetched, [team + '/cdn-cgi/access/certs'], name);
    assert.equal(logs[0].access, 'unverifiable', name);
  }
});

test('the key set is fetched once and then reused', async () => {
  const {environment, team} = isolated();
  const first = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({iss: team})});
  const second = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({iss: team})});
  assert.deepEqual([first.response.status, second.response.status], [200, 200]);
  assert.deepEqual([first.fetched.length, second.fetched.length], [1, 0]);
});

// jose refetches on an unknown kid, but at most once every 30 s. A key that appears inside
// that window is refused until it passes; after it, the new key is picked up without a deploy.
test('a rotated signing key is picked up by refetching the key set after the cooldown', async t => {
  t.mock.timers.enable({apis: ['Date'], now: Date.now()});
  const {environment, team} = isolated();
  let published = [KEY_A];
  const keys = () => publishing(published)();
  const before = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({iss: team}), keys});
  assert.equal(before.response.status, 200);
  published = [KEY_B, KEY_A];
  const early = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({iss: team}, {key: KEY_B}), keys});
  assert.equal(early.response.status, 403);
  assert.equal(early.fetched.length, 0);
  t.mock.timers.tick(31_000);
  const after = await proxy(new Request(FRONT + '/api/portfolio'), undefined, environment, {token: await mint({iss: team}, {key: KEY_B}), keys});
  assert.equal(after.response.status, 200);
  assert.equal(after.fetched.length, 1);
  assert.equal(after.sent.length, 1);
});

// app.js reloads the page on any text/html reply, taking it for an Access redirect. Each of
// these must reach it as JSON with a message instead.
test('edge timeouts, platform error pages, redirects and network failures become JSON errors', async () => {
  const cases = [
    [() => new Response('<html>524</html>', {status: 524, headers: {'content-type': 'text/html'}}), 504, 'upstream_timeout'],
    [() => new Response('<html>Service Unavailable</html>', {status: 503, headers: {'content-type': 'text/html'}}), 503, 'upstream_error'],
    [() => new Response('rate exceeded', {status: 429}), 429, 'upstream_error'],
    [() => new Response(null, {status: 302, headers: {location: 'https://accounts.google.com/'}}), 502, 'upstream_error'],
    [() => { throw new TypeError('network'); }, 502, 'upstream_unreachable'],
  ];
  for (const [reply, status, code] of cases) {
    const {response} = await proxy(new Request(FRONT + '/api/portfolio/refresh', {method: 'POST', body: '{}'}), reply);
    assert.equal(response.status, status, code);
    assert.match(response.headers.get('content-type'), /^application\/json/);
    const data = await response.json();
    assert.equal(data.code, code);
    assert.ok(data.message);
  }
});

test('backend responses pass through with only the allowed headers', async () => {
  const conflict = await proxy(new Request(FRONT + '/api/portfolio', {method: 'PUT', body: '{}'}), () => Response.json(
    {code: 'revision_conflict', message: 'm', issues: []}, {status: 409, headers: {'Cache-Control': 'no-store', 'Server': 'Google Frontend', 'X-Cloud-Trace-Context': 'abc'}}));
  assert.equal(conflict.response.status, 409);
  assert.equal((await conflict.response.json()).code, 'revision_conflict');
  assert.equal(conflict.response.headers.get('cache-control'), 'no-store');
  assert.equal(conflict.response.headers.get('server'), null);
  assert.equal(conflict.response.headers.get('x-cloud-trace-context'), null);
  const xlsx = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  const bytes = new Uint8Array([0x50, 0x4b, 0x00, 0xff]);
  const template = await proxy(new Request(FRONT + '/api/templates/holdings.xlsx'), () => new Response(bytes, {headers: {'content-type': xlsx}}));
  assert.equal(template.response.headers.get('content-type'), xlsx);
  assert.deepEqual([...new Uint8Array(await template.response.arrayBuffer())], [...bytes]);
});

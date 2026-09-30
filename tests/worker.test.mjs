// C7-2: the finpo Worker's /api/* proxy, run in Node with the upstream fetch replaced.
// The cross-language cases hand what the Worker actually sent to web_auth.Auth, the same
// code Cloud Run runs, so a drift on either side fails here rather than as a 401 in the cloud.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import worker from '../worker/index.js';

const SECRET = 'c7-2-test-secret-that-is-at-least-32-bytes';
const UPSTREAM = 'https://stock-quote-896096883650.asia-northeast1.run.app';
const FRONT = 'https://finpo.drhiromu.workers.dev';
const env = {PROXY_HMAC_SECRET: SECRET, UPSTREAM_ORIGIN: UPSTREAM};

async function proxy(request, reply = () => Response.json({ok: true}), environment = env) {
  const sent = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    sent.push({url: new URL(url), init, body: init.body === undefined ? new Uint8Array() : new Uint8Array(init.body)});
    return reply();
  };
  try {
    return {response: await worker.fetch(request, environment), sent};
  } finally {
    globalThis.fetch = original;
  }
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

"""Security boundaries: independent signatures, tampering, rotation and restart."""
import hashlib
import hmac

import pytest
from starlette.testclient import TestClient
from stock_quote_fetcher import web
from stock_quote_fetcher.web_auth import Auth, SESSION_TTL

CURRENT = 'current-test-secret-' * 3
OLD = 'previous-test-secret-' * 3
NOW = 1800000000


def signed(method, target, body=b'', secret=CURRENT, timestamp=str(NOW)):
    message = f'{timestamp}|{method}|{target}|{hashlib.sha256(body).hexdigest()}'.encode()
    return {'X-Timestamp': timestamp, 'X-Signature': hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()}


@pytest.fixture
def client():
    auth = Auth(CURRENT, OLD, clock=lambda: NOW)
    web.app.state.auth = auth
    class Service:
        calls = 0
        def get(self):
            self.calls += 1
            return {'ok': True}
        def save(self, document):
            self.calls += 1
            return document
        def refresh(self):
            self.calls += 1
            return {'ok': True}
    web.app.state.service = Service()
    with TestClient(web.Guard(web.app, {'testserver'}, {'https://front.test'}, auth)) as client:
        yield client


@pytest.mark.parametrize('method,path', [('GET','/api/session'),('GET','/api/portfolio'),('PUT','/api/portfolio'),('POST','/api/portfolio/refresh'),('GET','/api/unknown')])
def test_unsigned_denied_before_service(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json()['code'] == 'unauthorized'
    assert web.app.state.service.calls == 0


@pytest.mark.parametrize('secret', [CURRENT, OLD])
def test_signed_reads_and_raw_writes(client, secret):
    target = '/api/portfolio?x=%E5%8F%B0&x=two%20words'
    raw = b'{ "revision" : 2, "name": "test" }'
    headers = signed('PUT', target, raw, secret)
    headers.update({'Origin': 'https://front.test', 'X-Portfolio-Token': Auth(secret, clock=lambda: NOW).issue_session()})
    response = client.put(target, content=raw, headers=headers)
    assert response.status_code == 200
    assert response.json()['revision'] == 2


@pytest.mark.parametrize('change', ['body','query','method','path','signature','expired','future','timestamp','duplicate'])
def test_tampering_is_uniform_401(client, change):
    method, target, raw = 'PUT', '/api/portfolio?x=1&x=2', b'{"revision":2}'
    headers = signed(method, target, raw)
    headers.update({'Origin':'https://front.test','X-Portfolio-Token':web.app.state.auth.issue_session()})
    if change == 'body': raw = b'{ "revision":2}'
    if change == 'query': target = '/api/portfolio?x=2&x=1'
    if change == 'path': target = '/api/catalog/refresh'
    if change == 'method': method = 'POST'
    if change == 'signature': headers['X-Signature'] = 'z' * 64
    if change in ('expired','future','timestamp'):
        headers.update(signed(method,target,raw,timestamp={'expired':str(NOW-61),'future':str(NOW+61),'timestamp':'bad'}[change]))
    if change == 'duplicate': headers = list(headers.items()) + [('X-Timestamp',str(NOW))]
    response = client.request(method,target,content=raw,headers=headers)
    assert response.status_code == 401
    assert response.json() == {'code':'unauthorized','message':'請求未通過驗證。','issues':[]}
    assert web.app.state.service.calls == 0


def test_health_probe_unsigned(client):
    assert client.get('/healthz',headers={'Host':'probe'}).status_code == 200


def test_session_survives_restart_and_rotation_but_expires():
    token = Auth(OLD, clock=lambda: NOW).issue_session()
    assert Auth(OLD, clock=lambda: NOW+1).verify_session(token)
    assert Auth(CURRENT, OLD, clock=lambda: NOW+1).verify_session(token)
    assert not Auth(CURRENT, clock=lambda: NOW+1).verify_session(token)
    assert not Auth(OLD, clock=lambda: NOW+SESSION_TTL).verify_session(token)
    assert not Auth(OLD, clock=lambda: NOW-61).verify_session(token)
    assert not Auth(OLD, clock=lambda: NOW).verify_session(token+'a')


def test_session_cannot_be_used_as_proxy_signature(client):
    token = web.app.state.auth.issue_session()
    headers = {'X-Timestamp': token.split('.')[0], 'X-Signature': token.split('.')[1]}
    assert client.get('/api/session',headers=headers).status_code == 401


def test_expired_session_refused_then_refetched(client):
    raw = b'{}'
    headers = signed('PUT','/api/portfolio',raw)
    headers.update({'Origin':'https://front.test','X-Portfolio-Token':Auth(CURRENT,clock=lambda:NOW-SESSION_TTL).issue_session()})
    assert client.put('/api/portfolio',content=raw,headers=headers).json()['code'] == 'session_expired'
    assert web.app.state.service.calls == 0
    response = client.get('/api/session',headers=signed('GET','/api/session'))
    headers['X-Portfolio-Token'] = response.json()['token']
    assert client.put('/api/portfolio',content=raw,headers=headers).status_code == 200
    assert web.app.state.service.calls == 1


@pytest.mark.parametrize('value', [None,'','short'])
def test_missing_or_weak_current_fails_closed(monkeypatch,value):
    monkeypatch.delenv('PROXY_HMAC_SECRET',raising=False)
    if value is not None: monkeypatch.setenv('PROXY_HMAC_SECRET',value)
    with pytest.raises(ValueError): Auth.from_env()


def test_optional_previous_and_timestamp_boundaries():
    auth = Auth(CURRENT,clock=lambda:NOW)
    for delta in (-60,60): assert auth.timestamp_valid(str(NOW+delta))
    for value in ('NaN','-1','1'*100,' 1800000000'): assert not auth.timestamp_valid(value)
    with pytest.raises(ValueError): Auth(CURRENT,'short')

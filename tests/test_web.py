"""HTTP-layer tests for the ASGI dashboard: guard, routing, error mapping and body limits."""
import json

import pytest
from starlette.testclient import TestClient

from stock_quote_fetcher import web
from stock_quote_fetcher.web_input import MAX_UPLOAD, WebError

TOKEN = 'test-token'
HOST = 'testserver'
WRITE = {'Origin': f'http://{HOST}', 'X-Portfolio-Token': TOKEN}


class FakeService:
    def __init__(self):
        self.calls = []
        self.error = None

    def _record(self, name, *args):
        self.calls.append((name, *args))
        if self.error is not None:
            raise self.error
        return {'called': name, 'args': [str(a) for a in args]}

    def get(self):
        return self._record('get')

    def valuation(self, market='ALL'):
        return self._record('valuation', market)

    def job(self, job_id):
        return self._record('job', job_id)

    def save(self, document):
        return self._record('save', json.dumps(document, sort_keys=True))

    def refresh(self, catalog_only=False):
        return self._record('refresh', catalog_only)


@pytest.fixture
def service():
    fake = FakeService()
    web.app.state.service, web.app.state.token = fake, TOKEN
    return fake


def build(hosts={HOST}, origins={f'http://{HOST}'}):
    return TestClient(web.Failsafe(web.Guard(web.app, hosts, origins, TOKEN)))


@pytest.fixture
def client(service):
    with build() as test_client:
        yield test_client


def test_session_returns_token(client):
    response = client.get('/api/session')
    assert response.status_code == 200
    assert response.json() == {'token': TOKEN}


def test_security_headers_on_every_response(client):
    for path in ('/api/portfolio', '/api/missing'):
        headers = client.get(path).headers
        assert headers['cache-control'] == 'no-store'
        assert headers['x-content-type-options'] == 'nosniff'
        assert headers['referrer-policy'] == 'no-referrer'
        assert "default-src 'none'" in headers['content-security-policy']


def test_read_routes_reach_the_service(client, service):
    assert client.get('/api/portfolio').json()['called'] == 'get'
    assert client.get('/api/portfolio/valuation?market=TW').json()['args'] == ['TW']
    assert client.get('/api/portfolio/valuation').json()['args'] == ['ALL']
    assert client.get('/api/jobs/abc-123').json()['args'] == ['abc-123']
    assert [name for name, *_ in service.calls] == ['get', 'valuation', 'valuation', 'job']


def test_repeated_query_parameter_takes_the_first_value(client):
    assert client.get('/api/portfolio/valuation?market=TW&market=US').json()['args'] == ['TW']


def test_template_is_an_xlsx_download(client):
    response = client.get('/api/templates/holdings.xlsx')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats')
    assert response.content[:2] == b'PK'


def test_static_routes_are_gone(client):
    for path in ('/', '/app.js', '/style.css'):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()['message'] == '找不到頁面。'


def test_messages_are_utf8_not_escaped(client):
    assert '找不到頁面。'.encode() in client.get('/').content


def test_unknown_method_is_indistinguishable_from_unknown_path(client):
    assert client.delete('/api/portfolio', headers=WRITE).json()['message'] == '找不到頁面。'


def test_foreign_host_is_refused(client):
    response = client.get('/api/portfolio', headers={'Host': 'evil.example'})
    assert response.status_code == 403
    assert response.json()['message'] == '拒絕不合法的 Host。'


@pytest.mark.parametrize('headers', [{}, {'Origin': 'http://evil.example', 'X-Portfolio-Token': TOKEN},
                                     {'Origin': f'http://{HOST}', 'X-Portfolio-Token': 'wrong'}])
def test_writes_need_origin_and_token(client, service, headers):
    response = client.put('/api/portfolio', headers=headers, content=b'{"revision": 0}')
    assert response.status_code == 403
    assert response.json()['message'] == '請從本機儀表板進行操作。'
    assert service.calls == []


def test_reads_need_no_token(client):
    assert client.get('/api/portfolio').status_code == 200


def test_save_passes_the_parsed_document(client, service):
    response = client.put('/api/portfolio', headers=WRITE, content=json.dumps({'revision': 3}).encode())
    assert response.status_code == 200
    assert service.calls == [('save', '{"revision": 3}')]


def test_refresh_routes_answer_202(client, service):
    assert client.post('/api/portfolio/refresh', headers=WRITE, content=b'{}').status_code == 202
    assert client.post('/api/catalog/refresh', headers=WRITE, content=b'{}').status_code == 202
    assert service.calls == [('refresh', False), ('refresh', True)]


def test_malformed_json_is_a_400(client, service):
    response = client.put('/api/portfolio', headers=WRITE, content=b'{not json')
    assert response.status_code == 400
    assert response.json() == {'message': '請求格式錯誤。'}
    assert service.calls == []


def test_undecodable_body_is_a_400(client):
    response = client.put('/api/portfolio', headers=WRITE, content=b'\xff\xfe\x00')
    assert response.status_code == 400
    assert response.json() == {'message': '請求格式錯誤。'}


def test_oversized_upload_is_refused(client, service):
    response = client.post(f'/api/imports/preview?filename=x.xlsx', headers=WRITE, content=b'x' * (MAX_UPLOAD + 1))
    assert response.status_code == 413
    assert response.json()['message'] == '檔案不得超過 5 MiB。'
    assert service.calls == []


def test_upload_cap_holds_without_content_length(client):
    def chunks():
        for _ in range((MAX_UPLOAD // 65536) + 2):
            yield b'x' * 65536

    response = client.post('/api/imports/preview?filename=x.xlsx', headers=WRITE, content=chunks())
    assert response.status_code == 413


def test_non_xlsx_upload_is_refused(client):
    response = client.post('/api/imports/preview?filename=holdings.csv', headers=WRITE, content=b'data')
    assert response.status_code == 400
    assert response.json()['message'] == '只接受 .xlsx 檔案。'


def test_service_weberror_keeps_status_and_payload(client, service):
    service.error = WebError('持股已在另一個視窗更新。請重新載入後再編輯。', code='revision_conflict', status=409)
    response = client.put('/api/portfolio', headers=WRITE, content=b'{"revision": 0}')
    assert response.status_code == 409
    assert response.json()['code'] == 'revision_conflict'


def test_unexpected_failure_is_a_503_without_detail(client, service):
    service.error = RuntimeError('connection to 2330.TW failed')
    response = client.get('/api/portfolio')
    assert response.status_code == 503
    assert response.json() == {'message': '服務暫不可用，請確認資料庫及設定後重試；未保存內容仍保留。'}
    assert '2330' not in response.text


def test_unexpected_failure_logs_only_type_and_route(client, service, capfd):
    service.error = RuntimeError('connection to 2330.TW failed')
    client.get('/api/portfolio')
    logged = capfd.readouterr()
    assert 'RuntimeError at GET /api/portfolio' in logged.err
    assert '2330' not in logged.err + logged.out


# C2-2: the allowlists come from the environment, and default to the loopback behaviour.

def test_defaults_are_loopback_only(monkeypatch):
    monkeypatch.delenv('WEB_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('WEB_ALLOWED_ORIGINS', raising=False)
    hosts, origins = web.access_rules(8765)
    assert hosts == {'localhost:8765', '127.0.0.1:8765'}
    assert origins == {'http://localhost:8765', 'http://127.0.0.1:8765'}


def test_environment_replaces_both_allowlists(monkeypatch):
    monkeypatch.setenv('WEB_ALLOWED_HOSTS', 'finpo-1.asia-northeast1.run.app , api.example')
    monkeypatch.setenv('WEB_ALLOWED_ORIGINS', 'https://finpo.drhiromu.workers.dev')
    hosts, origins = web.access_rules(8765)
    assert hosts == {'finpo-1.asia-northeast1.run.app', 'api.example'}
    assert origins == {'https://finpo.drhiromu.workers.dev'}


def test_host_check_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setenv('WEB_ALLOWED_HOSTS', '*')
    hosts, _ = web.access_rules(8765)
    assert hosts == web.ANY_HOST


@pytest.mark.parametrize('name, value', [
    ('WEB_ALLOWED_HOSTS', ''),
    ('WEB_ALLOWED_HOSTS', ' , '),
    ('WEB_ALLOWED_HOSTS', 'http://localhost:8765'),
    ('WEB_ALLOWED_ORIGINS', ''),
    ('WEB_ALLOWED_ORIGINS', 'localhost:8765'),
    ('WEB_ALLOWED_ORIGINS', 'https://example.test/app'),
    ('WEB_ALLOWED_ORIGINS', '*'),
    ('WEB_ALLOWED_ORIGINS', 'https://good.test,*'),
])
def test_invalid_allowlists_fail_at_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(web.ConfigError):
        web.access_rules(8765)


def test_wildcard_host_still_answers_a_foreign_host(service):
    with build(hosts=web.ANY_HOST) as client:
        assert client.get('/api/portfolio', headers={'Host': 'finpo-1.run.app'}).status_code == 200


def test_wildcard_host_does_not_relax_the_origin_check(service):
    with build(hosts=web.ANY_HOST) as client:
        response = client.put('/api/portfolio', headers={'X-Portfolio-Token': TOKEN}, content=b'{}')
    assert response.status_code == 403
    assert service.calls == []


def test_configured_origin_is_accepted(service):
    edge = 'https://finpo.drhiromu.workers.dev'
    with build(hosts=web.ANY_HOST, origins={edge}) as client:
        response = client.put('/api/portfolio', content=b'{"revision": 1}',
                              headers={'Origin': edge, 'X-Portfolio-Token': TOKEN})
    assert response.status_code == 200
    assert service.calls == [('save', '{"revision": 1}')]


@pytest.mark.parametrize('header', ['X-Forwarded-Host', 'X-Forwarded-Server', 'Forwarded'])
def test_forwarded_headers_cannot_pass_the_host_check(client, header):
    response = client.get('/api/portfolio', headers={'Host': 'evil.example', header: HOST})
    assert response.status_code == 403
    assert response.json()['message'] == '拒絕不合法的 Host。'


# C2-3: the listening port comes from the platform when the operator does not fix one.

def test_explicit_port_beats_the_environment(monkeypatch):
    monkeypatch.setenv('PORT', '8080')
    assert web.listen_port(9000) == 9000


def test_platform_port_is_used_when_no_port_is_given(monkeypatch):
    monkeypatch.setenv('PORT', '8080')
    assert web.listen_port(None) == 8080


def test_port_falls_back_to_the_local_default(monkeypatch):
    monkeypatch.delenv('PORT', raising=False)
    assert web.listen_port(None) == web.DEFAULT_PORT == 8765


@pytest.mark.parametrize('value', ['', 'http', '0', '65536', '-1', '8080 '])
def test_unusable_platform_port_fails_at_startup(monkeypatch, value):
    monkeypatch.setenv('PORT', value)
    with pytest.raises(web.ConfigError):
        web.listen_port(None)


# Health check: answers from the process alone and bypasses the guard.

def test_health_check_answers_ok(client):
    response = client.get(web.HEALTH_PATH)
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_health_check_never_touches_the_service(client, service):
    service.error = RuntimeError('database is down')
    assert client.get(web.HEALTH_PATH).status_code == 200
    assert service.calls == []


def test_health_check_ignores_the_host_allowlist(client):
    response = client.get(web.HEALTH_PATH, headers={'Host': 'probe.internal'})
    assert response.status_code == 200


def test_health_check_is_outside_the_api_namespace():
    # C3-1 will sign every /api/ request; a platform probe cannot sign, so it must stay out.
    assert not web.HEALTH_PATH.startswith('/api')

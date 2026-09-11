"""Opt-in integration evidence; only modifies the dedicated dashboard_test schema."""
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
import time
import httpx

from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.web import Handler
from stock_quote_fetcher.web_input import template_xlsx


service = Dashboard(Path('/input/config.toml'), 'dashboard_test')
server = ThreadingHTTPServer(('127.0.0.1', 8766), Handler)
server.service, server.token, server.public_port = service, 'integration-token', 8766
Thread(target=server.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:8766'
headers = {'Origin': base, 'X-Portfolio-Token': 'integration-token'}
with httpx.Client(base_url=base, timeout=60) as client:
    assert client.get('/').status_code == 200
    assert client.get('/app.js').status_code == 200
    assert client.get('/api/portfolio', headers={'Host':'evil.example'}).status_code == 403
    assert client.put('/api/portfolio', json={}).status_code == 403
    p = client.get('/api/portfolio').json()
    preview = client.post('/api/imports/preview?filename=holdings.xlsx', content=template_xlsx(), headers=headers)
    assert preview.status_code == 200, preview.text
    rows = preview.json()['rows']
    assert not preview.json()['issues'] and rows[0]['ticker'] == '0050'
    response = client.put('/api/portfolio', json={'revision':p['revision'],'rows':rows,'fx':'30'}, headers=headers)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert client.put('/api/portfolio', json={'revision':p['revision'],'rows':[]}, headers=headers).status_code == 409
    bad = client.put('/api/portfolio', json={'revision':saved['revision'],'rows':[{'ticker':'2330','quantity':'1.5','buy_price':'80'}]}, headers=headers)
    assert bad.status_code == 400
    assert client.get('/api/portfolio').json() == saved
    assert Dashboard(Path('/input/config.toml'), 'dashboard_test').get() == saved
    valuation = client.get('/api/portfolio/valuation')
    assert valuation.status_code == 200, valuation.text
    assert valuation.json()['portfolio_revision'] == saved['revision']
    job = client.post('/api/portfolio/refresh', json={}, headers=headers)
    assert job.status_code == 202, job.text
    job = job.json()
    duplicate = client.post('/api/portfolio/refresh', json={}, headers=headers).json()
    assert duplicate['job_id'] == job['job_id']
    changed = client.put('/api/portfolio', json={'revision':saved['revision'],'rows':rows,'fx':'31'}, headers=headers).json()
    for _ in range(100):
        state = client.get('/api/jobs/'+job['job_id']).json()
        if state['status'] not in ('running','queued'):
            break
        time.sleep(1)
    assert state['status'] in ('succeeded','partial','failed'), state
    assert client.get('/api/portfolio').json() == changed
    result = client.get('/api/portfolio/valuation').json()
    assert result['portfolio_revision'] == changed['revision']
    print({'api':'passed','upload':'passed','conflict':'passed','restart_persistence':'passed',
           'job_deduplication':'passed','revision_protection':'passed','real_quote_job':state['status'],
           'coverage':result['coverage'],'count':result['count']})
server.shutdown()

"""Portfolio transactions on the same disposable DB fixture as CLI integration tests."""
from threading import Lock

import pytest

from test_storage import db
from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.config import QuoteConfig, InstrumentCatalogConfig
from stock_quote_fetcher.instruments import CatalogInstrument
from stock_quote_fetcher.storage import Storage
from stock_quote_fetcher.web_input import WebError


@pytest.fixture
def service(db, monkeypatch):
    cfg, _ = db
    s = Dashboard.__new__(Dashboard)
    s.db = s.source = cfg
    s.quote_config, s.catalog_config, s.mutex = QuoteConfig(), InstrumentCatalogConfig(), Lock()
    entries = (CatalogInstrument('us:NASDAQ:AAPL','AAPL','US','USD','NASDAQ','stock','Apple',{'yahoo':'AAPL'}),)
    monkeypatch.setattr(s, 'catalog', lambda: entries)
    s.initialize()
    return s


def body(revision=0):
    return {'revision':revision,'rows':[{'ticker':'AAPL','quantity':'2','buy_price':'8'}],'fx':'30'}


def test_save_conflict_and_restart(service):
    saved = service.save(body())
    assert saved['revision'] == 1
    assert service.get() == saved
    with pytest.raises(WebError) as exc:
        service.save(body())
    assert exc.value.status == 409
    assert service.get() == saved


def test_verified_otc_save_round_trip(service):
    request = body()
    request['rows'] = [{'ticker':'IFNNY','quantity':'8.554','buy_price':'40.88'}]
    saved = service.save(request)
    assert service.get() == saved
    assert saved['instruments']['IFNNY']['exchange'] == 'OTCQX'
    assert saved['instruments']['IFNNY']['provider_symbols']['yahoo'] == 'IFNNY'
    assert saved['rows'] == request['rows']
    service.initialize()
    assert service.get() == saved


def test_invalid_never_replaces(service):
    saved = service.save(body())
    bad = body(1); bad['rows'][0]['ticker'] = 'NOT_A_SUPPORTED_SECURITY'
    with pytest.raises(WebError): service.save(bad)
    assert service.get() == saved


def test_failed_job_does_not_overwrite_new_revision(service):
    saved = service.save(body())
    new = service.save(body(1) | {'fx':'31'})
    job = {'job_id':'lock-test','portfolio_revision':1,'created_at':'2026-09-09T00:00:00+00:00','status':'queued'}
    with Storage(service.db) as lock:
        lock.acquire_lock()
        service.run_job(job, saved)
    assert service.job('lock-test')['status'] == 'failed'
    assert service.get() == new


def test_recover_interrupted_job(service):
    service.put_job({'job_id':'interrupted','status':'running'})
    service.recover_jobs()
    assert service.job('interrupted')['status'] == 'failed'


def test_empty_and_missing_fx(service):
    saved = service.save(body() | {'fx':None})
    value = service.valuation()
    assert value['needs_fx'] and value['total'] is None
    assert service.save({'revision':saved['revision'],'rows':[],'fx':None})['rows'] == []


def test_save_does_not_require_collector_lock(service):
    with Storage(service.db) as collector:
        collector.acquire_lock()
        assert service.save(body())['revision'] == 1

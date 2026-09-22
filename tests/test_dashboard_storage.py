"""Portfolio transactions on the same disposable DB fixture as CLI integration tests."""
from datetime import UTC, datetime, timedelta

import pytest
from psycopg import sql

from test_storage import db
from stock_quote_fetcher.dashboard import Dashboard, LOST_MESSAGE
from stock_quote_fetcher.config import QuoteConfig, InstrumentCatalogConfig, RefreshConfig
from stock_quote_fetcher.instruments import CatalogInstrument
from stock_quote_fetcher.storage import Storage
from stock_quote_fetcher.web_input import WebError


@pytest.fixture
def service(db, monkeypatch):
    cfg, _ = db
    s = Dashboard.__new__(Dashboard)
    s.db = s.source = cfg
    s.quote_config, s.catalog_config = QuoteConfig(), InstrumentCatalogConfig()
    s.refresh_config = RefreshConfig()
    s.instance = 'instance-a'
    entries = (CatalogInstrument('us:NASDAQ:AAPL','AAPL','US','USD','NASDAQ','stock','Apple',{'yahoo':'AAPL'}),)
    monkeypatch.setattr(s, 'catalog', lambda: entries)
    s.initialize()
    return s


@pytest.fixture
def second(service, monkeypatch):
    """A second instance on the same schema: a Cloud Run rollout serving two revisions."""
    other = Dashboard.__new__(Dashboard)
    other.db = other.source = service.db
    other.quote_config, other.catalog_config = QuoteConfig(), InstrumentCatalogConfig()
    other.refresh_config = RefreshConfig()
    other.instance = 'instance-b'
    monkeypatch.setattr(other, 'catalog', service.catalog)
    return other


def stamp(seconds):
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def quote_count(service):
    with Storage(service.db) as s:
        return s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(s.table('quotes'))).fetchone()['n']


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


def test_a_live_lease_is_never_declared_failed(service):
    """C4-4: an unexpired job belongs to a running instance, possibly another revision."""
    service.put_job({'job_id':'alive','status':'running','owner':'instance-b',
                     'lease_expires_at':stamp(120),'created_at':stamp(-5)})
    assert service.recover_jobs() == []
    assert service.job('alive')['status'] == 'running'


def test_an_expired_lease_is_reclaimed(service):
    service.put_job({'job_id':'lost','status':'running','owner':'instance-b',
                     'lease_expires_at':stamp(-1),'created_at':stamp(-600)})
    assert [job['job_id'] for job in service.recover_jobs()] == ['lost']
    recovered = service.job('lost')
    assert recovered['status'] == 'failed' and recovered['message'] == LOST_MESSAGE
    assert recovered['completed_at']


def test_expired_lease_reads_as_failed_before_any_sweep(service):
    """A poller must never watch a dead job sit in 'running'."""
    service.put_job({'job_id':'stale','status':'running','owner':'instance-b',
                     'lease_expires_at':stamp(-1),'created_at':stamp(-600)})
    assert service.job('stale')['status'] == 'failed'


def test_second_instance_does_not_duplicate_a_claimed_job(service, second):
    """C4-3: the claim is atomic in the database, not in one process's memory."""
    saved = service.save(body())
    job, mine = service.claim(saved, False)
    assert mine and job['owner'] == 'instance-a'
    same, theirs = second.claim(saved, False)
    assert not theirs and same['job_id'] == job['job_id'] and same['owner'] == 'instance-a'


def test_second_instance_claims_once_the_lease_has_run_out(service, second):
    saved = service.save(body())
    job, _ = service.claim(saved, False)
    # A real lease outlives the cooldown, so an expired one is always older than 60s too.
    job.update(lease_expires_at=stamp(-1), created_at=stamp(-600))
    service.put_job(job)
    fresh, mine = second.claim(saved, False)
    assert mine and fresh['owner'] == 'instance-b' and fresh['job_id'] != job['job_id']
    assert service.job(job['job_id'])['status'] == 'failed'


def test_lease_always_outlives_the_cooldown(service):
    """Otherwise reclaiming a crashed job would immediately hit its own cooldown."""
    assert service.lease_seconds > 60


def test_cooldown_holds_across_instances(service, second):
    """C4-5: the 60s window is read from the row, so a second instance sees it too."""
    saved = service.save(body())
    job, _ = service.claim(saved, False)
    job.update(status='succeeded', completed_at=stamp(0))
    service.put_job(job)
    with pytest.raises(WebError) as exc:
        second.claim(saved, False)
    assert exc.value.status == 429 and exc.value.payload['code'] == 'cooldown'


def cut_the_clock(monkeypatch):
    """Deadline set from the first reading, already spent by the second."""
    ticks = iter([0.0] + [100.0] * 50)
    monkeypatch.setattr('stock_quote_fetcher.dashboard.monotonic', lambda: next(ticks))


def test_refresh_stops_at_the_deadline_and_keeps_stored_quotes(service, monkeypatch):
    """C4-1 and C4-6: the deadline cuts the run before any provider call; nothing is lost."""
    saved = service.save(body())
    before = quote_count(service)
    cut_the_clock(monkeypatch)
    service.refresh_config = RefreshConfig(deadline_seconds=1)
    job = service.refresh()
    assert job['status'] == 'failed' and '未在時限內處理' in job['message']
    assert job['completed_at'] and quote_count(service) == before
    assert service.get() == saved


def test_tickers_beyond_the_cap_are_reported_not_dropped(service, monkeypatch):
    entries = (CatalogInstrument('us:NASDAQ:AAPL','AAPL','US','USD','NASDAQ','stock','Apple',{'yahoo':'AAPL'}),
               CatalogInstrument('us:NASDAQ:MSFT','MSFT','US','USD','NASDAQ','stock','Microsoft',{'yahoo':'MSFT'}))
    monkeypatch.setattr(service, 'catalog', lambda: entries)
    request = body()
    request['rows'] = [{'ticker':'AAPL','quantity':'2','buy_price':'8'},
                       {'ticker':'MSFT','quantity':'1','buy_price':'9'}]
    service.save(request)
    cut_the_clock(monkeypatch)
    service.refresh_config = RefreshConfig(deadline_seconds=1, max_tickers=1)
    message = service.refresh()['message']
    assert '0/2 檔有可用報價' in message and '1 檔超出本次上限' in message

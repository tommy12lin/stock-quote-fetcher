"""Portfolio transactions on the same disposable DB fixture as CLI integration tests."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from psycopg import sql

from test_storage import db
from stock_quote_fetcher.dashboard import Dashboard, LOST_MESSAGE
from stock_quote_fetcher.config import QuoteConfig, InstrumentCatalogConfig, RefreshConfig
from stock_quote_fetcher.instruments import CatalogInstrument
from stock_quote_fetcher.models import Quote, FetchResult, FetchStatus
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


TWO = (CatalogInstrument('us:NASDAQ:AAPL','AAPL','US','USD','NASDAQ','stock','Apple',{'yahoo':'AAPL'}),
       CatalogInstrument('us:NASDAQ:MSFT','MSFT','US','USD','NASDAQ','stock','Microsoft',{'yahoo':'MSFT'}))


def seed_quote(service, instrument_id, ticker, received_at):
    """One real stored quote, so staleness ordering is read from the table it will use."""
    with Storage(service.db) as s:
        s.acquire_lock()
        run, cycle, attempt = uuid4(), uuid4(), uuid4()
        s.start_run(run, input_text=f'ticker,quantity,buy_price\n{ticker},1,1\n', config={}, image_id='test-image')
        s.start_cycle(cycle, run, market='US', scheduled_at=received_at)
        s.start_attempt(attempt, cycle, provider='yahoo', instrument_id=instrument_id, ticker=ticker, attempt_number=1)
        q = Quote(instrument_id, ticker, ticker, 'US', 'USD', 'yahoo', Decimal('10'), 'last_trade',
                  received_at, received_at, None, 'regular', 'second', asset_type='stock')
        s.finish_attempt(attempt, FetchResult(instrument_id, 'yahoo', FetchStatus.SUCCESS, q),
                         elapsed_ms=10, quote_id=uuid4())


def two_holdings(service, monkeypatch):
    monkeypatch.setattr(service, 'catalog', lambda: TWO)
    request = body()
    request['rows'] = [{'ticker':'AAPL','quantity':'2','buy_price':'8'},
                       {'ticker':'MSFT','quantity':'1','buy_price':'9'}]
    service.save(request)
    return request


def ordered_tickers(service):
    from stock_quote_fetcher.web_input import validate_rows
    p = service.get()
    holdings = validate_rows(p['rows'])
    resolved, _ = service.resolve(holdings)
    with Storage(service.db) as s:
        return [h.ticker for h in service.order_by_staleness(holdings, resolved, s)]


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
    two_holdings(service, monkeypatch)
    cut_the_clock(monkeypatch)
    service.refresh_config = RefreshConfig(deadline_seconds=1, max_tickers=1)
    message = service.refresh()['message']
    assert '0/2 檔有可用報價' in message and '1 檔超出本次上限' in message


def test_never_quoted_holdings_are_the_stalest(service, monkeypatch):
    two_holdings(service, monkeypatch)
    seed_quote(service, 'us:NASDAQ:AAPL', 'AAPL', datetime.now(UTC))
    # MSFT has no quote at all, so it must come before an AAPL quoted a moment ago.
    assert ordered_tickers(service) == ['MSFT', 'AAPL']


def test_order_rotates_so_a_capped_refresh_reaches_every_holding(service, monkeypatch):
    """The defect this guards: slicing a fixed order left the tail permanently stale."""
    two_holdings(service, monkeypatch)
    seed_quote(service, 'us:NASDAQ:AAPL', 'AAPL', datetime.now(UTC) - timedelta(hours=2))
    seed_quote(service, 'us:NASDAQ:MSFT', 'MSFT', datetime.now(UTC) - timedelta(minutes=5))
    assert ordered_tickers(service) == ['AAPL', 'MSFT']
    # A capped refresh would take AAPL. Once AAPL is fresh, MSFT becomes the stalest.
    seed_quote(service, 'us:NASDAQ:AAPL', 'AAPL', datetime.now(UTC))
    assert ordered_tickers(service) == ['MSFT', 'AAPL']


def test_equal_staleness_keeps_the_saved_order(service, monkeypatch):
    two_holdings(service, monkeypatch)
    assert ordered_tickers(service) == ['AAPL', 'MSFT']


# C7-6 R1: a full listing refresh took 135 s from Cloud Run against a 125 s edge limit,
# outside the refresh deadline. With refresh_in_request off it must never run in a request.

def out_of_band(service, monkeypatch, *, listing=True):
    service.catalog_config = InstrumentCatalogConfig(refresh_in_request=False)
    # Failed is a BaseException: run_job's broad except cannot swallow it into a job row.
    monkeypatch.setattr('stock_quote_fetcher.catalog.fetch_all',
                        lambda config: pytest.fail('official listing fetched inside a request'))
    if not listing:
        def expired():
            raise WebError('expired', code='catalog_unavailable', status=503)
        monkeypatch.setattr(service, 'catalog', expired)


def job_rows(service):
    with Storage(service.db) as s:
        return s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(s.table('refresh_jobs'))).fetchone()['n']


def fetched_quote(monkeypatch):
    from stock_quote_fetcher import quoting
    from stock_quote_fetcher.providers import Operation
    def fetch(instrument, provider, config, timeout):
        stamp = datetime.now(UTC)
        q = Quote(instrument.instrument_id, instrument.ticker, instrument.provider_symbols['yahoo'], instrument.market,
                  instrument.currency, provider, Decimal('10'), 'last_trade', stamp, stamp, None, 'regular', 'second')
        return Operation(FetchResult(instrument.instrument_id, provider, 'success', q), {'parser_version': 'fixture'})
    monkeypatch.setattr(quoting, 'fetch_one', fetch)


def test_listing_refresh_from_the_page_is_refused_before_any_job(service, monkeypatch):
    service.save(body())
    out_of_band(service, monkeypatch)
    with pytest.raises(WebError) as exc:
        service.refresh(catalog_only=True)
    assert exc.value.status == 409 and exc.value.payload['code'] == 'catalog_refresh_offline'
    assert job_rows(service) == 0


def test_expired_listing_quotes_from_saved_identities_without_fetching_it(service, monkeypatch):
    service.save(body())
    out_of_band(service, monkeypatch, listing=False)
    fetched_quote(monkeypatch)
    before = quote_count(service)
    job = service.refresh()
    assert job['status'] == 'succeeded', job['message']
    assert quote_count(service) == before + 1


def test_expired_listing_without_saved_identities_fails_fast(service, monkeypatch):
    service.save(body())
    with Storage(service.db) as s:  # a portfolio saved before identities were stored with it
        s.conn.execute(sql.SQL("UPDATE {} SET document=document-'instruments' WHERE id=1").format(s.table('portfolio')))
    out_of_band(service, monkeypatch, listing=False)
    from stock_quote_fetcher import quoting
    def never(instrument, provider, config, timeout):
        pytest.fail('quoted a holding with no saved identity')
    monkeypatch.setattr(quoting, 'fetch_one', never)
    job = service.refresh()
    assert job['status'] == 'failed' and '管理者' in job['message'] and job['completed_at']


def test_expired_listing_message_matches_who_can_refresh_it(service):
    # The fixture's catalog is a stub; the real one reads the (empty) test schema.
    with pytest.raises(WebError, match='更新股票清單'):
        Dashboard.catalog(service)
    service.catalog_config = InstrumentCatalogConfig(refresh_in_request=False)
    with pytest.raises(WebError, match='管理者') as exc:
        Dashboard.catalog(service)
    assert '更新股票清單' not in exc.value.payload['message']

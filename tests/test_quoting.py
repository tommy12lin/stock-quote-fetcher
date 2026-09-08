from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import subprocess
from uuid import uuid4

import pytest

from stock_quote_fetcher.config import QuoteConfig, ConfigurationError, load_quote_config
from stock_quote_fetcher.models import Instrument, Holding, QualityFlag as F
from stock_quote_fetcher.providers import normalize, fetch_one, failure, Operation
from stock_quote_fetcher.quality import assess, bounds
from stock_quote_fetcher.quoting import QuoteRunner, compare

US = Instrument('us:nasdaq:AAPL','AAPL','US','USD',{'yahoo':'AAPL'},'NASDAQ-Q','stock')
TW = Instrument('tw:2330','2330','TW','TWD',{'yahoo':'2330.TW'},'TWSE','stock')
NOW = datetime(2026,9,8,15,0,tzinfo=UTC)


def payload(instrument=US, stamp=NOW):
    return {'symbol':instrument.provider_symbols['yahoo'],'currency':instrument.currency,
            'quoteType':'EQUITY','regularMarketPrice':'200.12345678901234567890123456789',
            'regularMarketTime':int(stamp.timestamp()),'exchangeDataDelayedBy':0,
            'exchangeTimezoneName':'America/New_York' if instrument.market == 'US' else 'Asia/Taipei',
            'marketState':'REGULAR'}


def test_normalization_exact_and_identity():
    q = normalize(US,'yahoo',payload(),NOW)
    assert q.price == Decimal(payload()['regularMarketPrice'])
    assert q.session == 'regular' and not q.quality_flags
    for key,value in [('symbol','OTHER'),('quoteType','MUTUALFUND'),('exchangeTimezoneName','UTC'),
                      ('regularMarketPrice',0),('regularMarketPrice','NaN'),('regularMarketTime',True)]:
        with pytest.raises((ValueError,ArithmeticError)):
            normalize(US,'yahoo',{**payload(),key:value},NOW)


def test_unknown_currency_future_and_older_time():
    assert F.CURRENCY_MISMATCH in normalize(US,'yahoo',{**payload(),'currency':'EUR'},NOW).quality_flags
    q = normalize(US,'yahoo',{**payload(),'regularMarketTime':None},NOW)
    assert q.quote_time is None and F.TIME_UNKNOWN in q.quality_flags
    q = normalize(US,'yahoo',{**payload(),'regularMarketTime':int(NOW.timestamp())+6},NOW)
    assert F.FUTURE_TIME in q.quality_flags
    q = normalize(US,'yahoo',{**payload(),'regularMarketTime':int(NOW.timestamp())-600},NOW)
    assert F.STALE in q.quality_flags


def test_closed_holiday_latest_close_not_stale():
    closed = datetime(2026,9,4,20,tzinfo=UTC)
    holiday = datetime(2026,9,7,15,tzinfo=UTC)
    q = normalize(US,'yahoo',payload(stamp=closed),holiday)
    assert q.session == 'closed' and F.MARKET_CLOSED in q.quality_flags
    assert F.STALE not in q.quality_flags


def test_opening_delay_preserves_prior_day_and_not_today_claim():
    closed = datetime(2026,9,7,5,30,tzinfo=UTC)
    now = datetime(2026,9,8,1,10,tzinfo=UTC)
    q = normalize(TW,'yahoo',{**payload(TW,closed),'exchangeDataDelayedBy':20},now)
    assert str(q.trading_date) == '2026-09-07'
    assert F.STALE not in q.quality_flags
    assert F.STALE in assess(q,as_of=datetime(2026,9,8,1,25,tzinfo=UTC)).quality_flags


def test_dst_early_close_and_outside_session():
    from datetime import date
    assert bounds('US',date(2026,3,6))[0].hour == 14
    assert bounds('US',date(2026,3,9))[0].hour == 13
    assert bounds('US',date(2026,11,27))[1].hour == 18
    post = datetime(2026,9,8,21,tzinfo=UTC)
    q = normalize(US,'finnhub',{'c':'200','t':int(post.timestamp())},post)
    assert q.session == 'unknown' and F.SESSION_UNKNOWN in q.quality_flags


def test_finnhub_unknown_delay_and_official_date_only():
    q = normalize(US,'finnhub',{'c':'200.123','t':int(NOW.timestamp())},NOW)
    assert q.declared_delay_seconds is None and F.FRESHNESS_UNKNOWN in q.quality_flags
    assert F.TIME_UNKNOWN not in q.quality_flags
    q = normalize(TW,'twse',{'Code':'2330','ClosingPrice':'1,234.50','Date':'1150908'},NOW)
    assert q.price == Decimal('1234.50') and str(q.trading_date) == '2026-09-08'
    assert q.quote_time is None and q.time_precision == 'day'


def test_adapter_deadline_kills_worker(monkeypatch):
    def timeout(*a,**kw):
        assert kw['timeout'] == 0.5
        raise subprocess.TimeoutExpired(a[0],kw['timeout'])
    monkeypatch.setattr(subprocess,'run',timeout)
    assert fetch_one(US,'yahoo',QuoteConfig(),0.5).result.status == 'timeout'


def test_config_rejects_unsupported_and_secrets(tmp_path):
    for kwargs in ({'valuation':'finnhub'},{'max_retries':3},{'operation_timeout_seconds':True},
                   {'comparison':('unknown',)},{'relaxed_providers':('yahoo',)},
                   {'relaxed_providers':('finnhub',)}):
        with pytest.raises(ConfigurationError):
            QuoteConfig(**kwargs)
    path = tmp_path/'config.toml'
    path.write_text('[providers]\napi_key="secret"\n')
    with pytest.raises(ConfigurationError) as caught:
        load_quote_config(path)
    assert 'secret' not in str(caught.value)


class FakeStorage:
    failed = False
    def __init__(self):
        self.attempts, self.results = [], []
    def start_attempt(self,identity,cycle,**kwargs):
        self.attempts.append(kwargs)
    def finish_attempt(self,identity,result,**kwargs):
        self.results.append((result,kwargs))
        return kwargs.get('quote_id') if result.quote else None


def test_retries_record_each_failure_and_no_parse_retry():
    db = FakeStorage()
    clock = [0]
    def sleep(n):
        clock[0] += n
    runner = QuoteRunner(db,QuoteConfig(),fetch=lambda i,p,c,t:failure(i,p,'network_error','network_error'),
                         monotonic=lambda:clock[0],sleep=sleep)
    assert runner.collect(uuid4(),US,'yahoo',50) == (None,None)
    assert [x['attempt_number'] for x in db.attempts] == [1,2,3]
    db = FakeStorage()
    runner = QuoteRunner(db,QuoteConfig(),fetch=lambda i,p,c,t:failure(i,p,'invalid_payload','schema'))
    runner.collect(uuid4(),US,'yahoo',runner.monotonic()+50)
    assert len(db.results) == 1


def test_429_cooldown_is_source_specific_and_budget_recorded():
    db = FakeStorage()
    calls = []
    def fetch(i,p,c,t):
        calls.append(p)
        fail = failure(i,p,'rate_limited','http_429')
        return Operation(fail.result,fail.evidence,100)
    runner = QuoteRunner(db,QuoteConfig(),fetch=fetch,monotonic=lambda:0,sleep=lambda _:None)
    runner.collect(uuid4(),US,'yahoo',50)
    runner.collect(uuid4(),US,'yahoo',50)
    runner.collect(uuid4(),US,'finnhub',50)
    runner.collect(uuid4(),US,'twse',0)
    assert calls == ['yahoo','finnhub']
    assert db.results[1][0].error == 'source_cooldown'
    assert db.results[1][1]['provider_evidence']['effective_cooldown_seconds'] > 0
    assert db.results[-1][0].error == 'cycle_budget_exhausted'
    assert db.results[-1][1]['provider_evidence']['executed'] is False


def test_price_comparison_requires_alignment():
    a = normalize(US,'yahoo',payload(),NOW)
    b = normalize(US,'finnhub',{'c':str(a.price),'t':int(NOW.timestamp())},NOW)
    assert compare(a,b,'AAPL','finnhub')['aligned']
    b = replace(b,quote_time=datetime(2026,9,8,14,59,tzinfo=UTC))
    assert not compare(a,b,'AAPL','finnhub')['aligned']
    a = normalize(TW,'yahoo',payload(TW,datetime(2026,9,8,5,30,tzinfo=UTC)),NOW)
    b = normalize(TW,'twse',{'Code':'2330','ClosingPrice':'100','Date':'1150908'},NOW)
    assert compare(a,b,'2330','twse')['aligned']
    assert not compare(replace(a,quote_time=datetime(2026,9,8,5,29,tzinfo=UTC)),b,'2330','twse')['aligned']


def test_invalid_csv_never_opens_database(monkeypatch,tmp_path):
    from stock_quote_fetcher.cli import main
    import stock_quote_fetcher.quoting as quoting
    monkeypatch.setattr(quoting,'Storage',lambda *a:pytest.fail('database accessed'))
    path = tmp_path/'bad.csv'
    path.write_text('ticker,buy_price,quantity\nAAPL,0,1\n')
    assert main(['quote','--input',str(path),'--config','missing.toml','--output',str(tmp_path/'out')]) == 2


def test_worker_auth_header_tls_and_secret_redaction(monkeypatch):
    import httpx
    import ssl
    from stock_quote_fetcher.provider_worker import fetch
    secret = 'unit-test-token-never-serialize'
    monkeypatch.setenv('FINNHUB_API_KEY',secret)
    def respond(request):
        assert request.headers['X-Finnhub-Token'] == secret
        assert secret not in str(request.url)
        return httpx.Response(401,headers={'content-type':'application/json'},json={'error':secret})
    real = httpx.Client
    def client(**kwargs):
        context = kwargs['verify']
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        return real(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx,'Client',client)
    result = fetch({'provider':'finnhub','symbol':'AAPL','timeout':1})
    assert result['status'] == 'provider_error' and secret not in str(result)


def test_worker_429_retry_after_and_whitelisted_payload(monkeypatch):
    import httpx
    from stock_quote_fetcher.provider_worker import fetch
    monkeypatch.setenv('FINNHUB_API_KEY','fixture')
    real = httpx.Client
    replies = iter([httpx.Response(429,headers={'Retry-After':'120'}),
                    httpx.Response(200,headers={'content-type':'application/json'},
                                   json={'c':200.25,'t':int(NOW.timestamp()),'unexpected':'excluded'})])
    monkeypatch.setattr(httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(lambda req:next(replies))))
    request = {'provider':'finnhub','symbol':'AAPL','timeout':1}
    assert fetch(request)['retry_after'] == 120
    result = fetch(request)
    assert result['payload'] == {'c':'200.25','t':int(NOW.timestamp())}


def test_worker_relaxed_tls_keeps_chain_and_hostname(monkeypatch):
    import ssl
    import httpx
    from stock_quote_fetcher.provider_worker import fetch
    class Context:
        verify_mode = ssl.CERT_REQUIRED
        check_hostname = True
        verify_flags = ssl.VERIFY_X509_STRICT
        def load_verify_locations(self,*,cafile):
            assert cafile == 'public-ca.crt'
    context = Context()
    monkeypatch.setattr(ssl,'create_default_context',lambda:context)
    real = httpx.Client
    def client(**kwargs):
        assert kwargs['verify'].verify_mode == ssl.CERT_REQUIRED
        assert kwargs['verify'].check_hostname
        assert not kwargs['verify'].verify_flags & ssl.VERIFY_X509_STRICT
        return real(transport=httpx.MockTransport(lambda r:httpx.Response(503)))
    monkeypatch.setattr(httpx,'Client',client)
    assert fetch({'provider':'twse','symbol':'2330','timeout':1,'company_ca_file':'public-ca.crt','relaxed':True})['status'] == 'network_error'


def test_real_subprocess_deadline_reaps_process(monkeypatch):
    import sys
    import time
    from stock_quote_fetcher.providers import fetch_one
    real = subprocess.run
    def slow_worker(args,**kwargs):
        return real([sys.executable,'-c','import time; time.sleep(10)'],**kwargs)
    monkeypatch.setattr(subprocess,'run',slow_worker)
    start = time.monotonic()
    assert fetch_one(US,'yahoo',QuoteConfig(),0.1).result.status == 'timeout'
    assert time.monotonic()-start < 2


def test_delay_above_supported_limit_is_degraded():
    q = normalize(US,'yahoo',{**payload(),'exchangeDataDelayedBy':25},NOW)
    assert F.STALE in q.quality_flags

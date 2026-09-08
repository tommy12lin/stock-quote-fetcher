"""Real PostgreSQL tests, opt-in against the disposable step-3 database only."""

from dataclasses import replace
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from stock_quote_fetcher.config import DatabaseConfig, ConfigurationError, load_database_config
from stock_quote_fetcher.models import FetchResult, FetchStatus, Quote
from stock_quote_fetcher.storage import Storage, StorageError, configuration_snapshot, lock_key


CSV = 'ticker,buy_price,quantity\nAAPL,180,2.5\n'
STAMP = datetime(2026, 9, 8, 14, 0, tzinfo=UTC)


def test_configuration_rejects_secret_and_invalid_values(tmp_path):
    path = tmp_path / 'config.toml'
    path.write_text('[database]\npassword="do-not-print"\n')
    with pytest.raises(ConfigurationError) as caught:
        load_database_config(path, {})
    assert 'do-not-print' not in str(caught.value)
    for changes in ({'schema': 123}, {'schema': 'public'}, {'schema': 'pg_catalog'}, {'schema': 'x;DROP'}, {'port': True}, {'connect_timeout': 0}, {'password': ''}):
        with pytest.raises(ConfigurationError):
            DatabaseConfig(**({'password': 'secret'} | changes))
    path.write_text('[database]\nport=5432\n')
    config = load_database_config(path, {'DB_PASSWORD': 'secret', 'DB_HOST': 'db', 'DB_PORT': '5433'})
    assert config.host == 'db' and config.port == 5433
    assert 'secret' not in repr(config)


def test_snapshot_hash_is_order_independent_and_secrets_rejected():
    a = {'providers': {'valuation':'yahoo','comparison':[]}}
    b = {'providers': {'comparison':[],'valuation':'yahoo'}}
    assert configuration_snapshot(a) == configuration_snapshot(b)
    for config in ({'database': {'password':'secret'}}, {'token':'secret'}, {'providers': {'valuation': {'api_key':'secret'}}}):
        with pytest.raises(ValueError):
            configuration_snapshot(config)
    assert lock_key('app') == lock_key('app')
    assert lock_key('app') != lock_key('other')
    assert -(2**63) <= lock_key('app') < 2**63


@pytest.fixture
def db():
    if os.environ.get('STOCK_POC_TEST_POSTGRES') != 'disposable-local':
        pytest.skip('requires explicitly opted-in disposable PostgreSQL container')
    # No configurable admin DSN: production credentials can never select this target.
    admin = psycopg.connect(host='stock-poc-test-db', dbname='postgres', user='postgres', password='stock-poc-isolated-test-only', autocommit=True)
    identity = 'test_' + uuid4().hex
    admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(identity), sql.Literal('test-password')))
    admin.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(identity),sql.Identifier(identity)))
    cfg = DatabaseConfig(host='stock-poc-test-db', name='postgres', schema=identity, user=identity, password='test-password')
    try:
        yield cfg, admin
    finally:
        admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(identity)))
        admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(identity)))
        admin.close()


@contextmanager
def collector(cfg):
    with Storage(cfg) as storage:
        storage.migrate()
        storage.check_schema()
        yield storage


def started(storage, input_text=CSV):
    run, cycle = uuid4(), uuid4()
    storage.start_run(run, input_text=input_text, config={}, image_id='test-image')
    storage.start_cycle(cycle, run, market='US', scheduled_at=STAMP)
    return run, cycle


def quote(price=Decimal('200.10')):
    return Quote('us-aapl','AAPL','AAPL','US','USD','yahoo',price,'last_trade',STAMP,STAMP,None,'regular','second')


def fetched(storage, cycle, q=None):
    q = q or quote()
    attempt, identity = uuid4(), uuid4()
    storage.start_attempt(attempt, cycle, provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
    result_id = storage.finish_attempt(attempt, FetchResult('us-aapl','yahoo',FetchStatus.SUCCESS,q),elapsed_ms=10,quote_id=identity)
    return attempt, result_id


def test_migrate_idempotent_schema_and_locks(db):
    cfg, _ = db
    with Storage(cfg) as a, Storage(cfg) as b:
        assert a.check_permissions(migration=True)['username'] == cfg.user
        assert a.migrate() == ['0001_initial.sql','0002_instrument_catalog.sql']
        assert a.migrate() == []
        a.check_schema()
        with pytest.raises(StorageError, match='另一個'):
            b.acquire_lock()
    with Storage(cfg) as b:
        b.acquire_lock()


@pytest.mark.parametrize('kind', ['checksum','future','missing'])
def test_schema_version_rejected(db, kind):
    cfg, admin = db
    with collector(cfg) as s:
        if kind == 'checksum':
            admin.execute(sql.SQL("UPDATE {}.schema_migrations SET checksum='changed'").format(sql.Identifier(cfg.schema)))
        elif kind == 'future':
            admin.execute(sql.SQL("INSERT INTO {}.schema_migrations VALUES ('9999_future.sql','hash','test',now())").format(sql.Identifier(cfg.schema)))
        else:
            admin.execute(sql.SQL('DELETE FROM {}.schema_migrations').format(sql.Identifier(cfg.schema)))
        with pytest.raises(StorageError, match='版本'):
            s.check_schema()


def test_migration_failure_rolls_back_ddl_and_version(db, monkeypatch):
    cfg, admin = db
    import stock_quote_fetcher.storage as module
    monkeypatch.setattr(module, 'migration_sources', lambda: [('0001_bad.sql', 'CREATE TABLE {schema}.probe(id int); SELECT 1/0;')])
    with Storage(cfg) as s:
        with pytest.raises(StorageError):
            s.migrate()
    assert admin.execute('SELECT to_regclass(%s),to_regclass(%s)', (cfg.schema+'.probe', cfg.schema+'.schema_migrations')).fetchone() == (None,None)


def test_exact_roundtrip_full_lifecycle_and_readonly(db):
    cfg, _ = db
    value = Decimal('123456789012345678901234567890.000000000000000000123')
    with collector(cfg) as s:
        run, cycle = started(s)
        _, quote_id = fetched(s,cycle,quote(value))
        with localcontext() as ctx:
            ctx.prec = 4
            report = s.finish_cycle(cycle,selected_quotes={'AAPL':quote_id})
        s.heartbeat(run)
        s.finish_run(run)
    with Storage(cfg) as reader:
        with reader.report_snapshot():
            saved = reader.read_run(run)
            assert saved['run']['status'] == 'completed'
            assert saved['quotes'][0]['price'] == value
            assert saved['quotes'][0]['received_at'] == STAMP
            assert saved['valuations'][0]['market_value'] == report.rows[0].market_value
            assert saved['totals'][0]['total'] == report.summaries[0].total
            assert reader.conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'on'
        with pytest.raises(StorageError):
            with reader.report_snapshot():
                reader.conn.execute(sql.SQL('DELETE FROM {}').format(reader.table('runs')))


@pytest.mark.parametrize('bad', ['NaN','Infinity','-Infinity','0','-1'])
def test_invalid_price_saved_as_failed_evidence(db,bad):
    cfg, _ = db
    with collector(cfg) as s:
        run, cycle = started(s)
        attempt, identity = fetched(s,cycle,quote(Decimal(bad)))
        assert identity is None
        assert s._one('fetch_attempts',attempt)['status'] == 'invalid_payload'
        report = s.finish_cycle(cycle,selected_quotes={})
        assert report.summaries[0].total is None


def test_attempt_failure_does_not_persist_secret_error(db):
    cfg, _ = db
    with collector(cfg) as s:
        _, cycle = started(s)
        attempt = uuid4()
        s.start_attempt(attempt,cycle,provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
        s.finish_attempt(attempt,FetchResult('us-aapl','yahoo','network_error',error='https://url/?token=secret'),elapsed_ms=5)
        assert 'secret' not in str(s._one('fetch_attempts',attempt))


def test_unfinished_recovered_without_fabricated_completion(db):
    cfg, _ = db
    with collector(cfg) as s:
        run, cycle = started(s)
        attempt = uuid4()
        s.start_attempt(attempt,cycle,provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
    with collector(cfg) as s:
        assert s.recover_incomplete() == {'fetch_attempts':1,'cycles':1,'runs':1}
        for table, identity in [('runs',run),('cycles',cycle),('fetch_attempts',attempt)]:
            row = s._one(table,identity)
            assert row['status'] == 'interrupted' and row['recovered_at'] is not None
        assert s._one('cycles',cycle)['completed_at'] is None
        assert s.recover_incomplete() == {'fetch_attempts':0,'cycles':0,'runs':0}


def test_disconnect_stops_session_and_releases_lock(db):
    cfg, admin = db
    with collector(cfg) as s:
        run, _ = started(s)
        pid = s.conn.info.backend_pid
        admin.execute('SELECT pg_terminate_backend(%s)',(pid,))
        with pytest.raises(StorageError):
            s.heartbeat(run)
        with pytest.raises(StorageError):
            s.start_run(uuid4(),input_text=CSV,config={},image_id='test')
    with collector(cfg) as s:
        assert s.recover_incomplete()['runs'] == 1


def test_completion_failure_rolls_back_values_and_status(db):
    cfg, admin = db
    with collector(cfg) as s:
        run, cycle = started(s)
        _, identity = fetched(s,cycle)
        # Force a failure after valuation rows have been inserted.
        admin.execute(sql.SQL('ALTER TABLE {}.valuation_totals ADD CHECK (known_subtotal < 1)').format(sql.Identifier(cfg.schema)))
        with pytest.raises(StorageError):
            s.finish_cycle(cycle,selected_quotes={'AAPL':identity})
    with Storage(cfg) as s:
        with s.report_snapshot():
            saved = s.read_run(run)
            assert saved['valuations'] == [] and saved['totals'] == []
            assert saved['cycles'][0]['status'] == 'running'


def test_privilege_error_is_redacted_and_fatal(db):
    cfg, admin = db
    with collector(cfg) as s:
        run, cycle = started(s)
        admin.execute(sql.SQL('ALTER TABLE {}.fetch_attempts OWNER TO postgres').format(sql.Identifier(cfg.schema)))
        with pytest.raises(StorageError) as error:
            s.start_attempt(uuid4(),cycle,provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
        assert cfg.password not in str(error.value)
        assert '42501' in str(error.value)


def test_cross_run_foreign_key_and_nonfinite_numeric(db):
    cfg, _ = db
    with collector(cfg) as s:
        a, ca = started(s)
        b, cb = started(s)
        holding = s.conn.execute(sql.SQL('SELECT id FROM {} WHERE run_id=%s').format(s.table('holdings')),(b,)).fetchone()['id']
        with pytest.raises(StorageError):
            with s.transaction():
                s._insert('valuations',dict(cycle_id=ca,holding_id=holding,run_id=a,quality_flags='[]'))
    with collector(cfg) as s:
        with pytest.raises(StorageError):
            with s.transaction():
                s.conn.execute(sql.SQL("UPDATE {} SET buy_price='NaN'").format(s.table('holdings')))


def test_campaign_schedule_atomicity_and_immutable_restart(db):
    cfg, _ = db
    with collector(cfg) as s:
        campaign, scheduled = uuid4(), uuid4()
        kwargs = dict(input_text=CSV,config={},planned_start=STAMP,planned_end=STAMP+timedelta(hours=1),
            scheduled_cycles=[dict(id=scheduled,market='US',scheduled_at=STAMP,window_type='regular')],
            source_instruments=[{'provider':'yahoo','instrument_id':'us-aapl'}],calendar_version='v1',schedule_version='v1',threshold_version='unconfirmed',maintenance_windows=[])
        s.create_campaign(campaign,**kwargs)
        run = uuid4()
        s.start_run(run,input_text=CSV,config={},image_id='test',campaign_id=campaign)
        s.start_cycle(uuid4(),run,market='US',scheduled_at=STAMP,scheduled_cycle_id=scheduled)
        with pytest.raises(ValueError,match='immutable'):
            s.start_run(uuid4(),input_text=CSV.replace('2.5','3'),config={},image_id='test',campaign_id=campaign)
        bad = uuid4()
        kwargs['scheduled_cycles'] = [dict(id=uuid4(),market='US',scheduled_at=STAMP-timedelta(seconds=1),window_type='regular')]
        with pytest.raises(ValueError,match='outside'):
            s.create_campaign(bad,**kwargs)
        assert s.conn.execute(sql.SQL('SELECT 1 FROM {} WHERE id=%s').format(s.table('campaigns')),(bad,)).fetchone() is None


def test_collector_requires_lock(db):
    cfg, _ = db
    with Storage(cfg) as s:
        with pytest.raises(StorageError,match='鎖'):
            s.start_run(uuid4(),input_text=CSV,config={},image_id='test')


def test_cache_reference_preserves_original_and_marks_usage(db):
    cfg, _ = db
    with collector(cfg) as s:
        run, cycle = started(s)
        _, identity = fetched(s,cycle)
        s.finish_cycle(cycle,selected_quotes={'AAPL':identity})
        second = uuid4()
        s.start_cycle(second,run,market='US',scheduled_at=STAMP+timedelta(minutes=1))
        report = s.finish_cycle(second,selected_quotes={'AAPL':identity},quality_flags={'AAPL':{'stale'}})
        assert {'cached','stale'} <= report.rows[0].quality_flags
        assert report.rows[0].quote.quote_time == STAMP
        assert report.summaries[0].completeness == 'degraded'
        assert s._one('quotes',identity)['quality_flags'] == []


def test_campaign_gaps_keep_future_and_restart_history(db):
    cfg, _ = db
    with collector(cfg) as s:
        campaign = uuid4()
        schedule = [dict(id=uuid4(),market='US',scheduled_at=STAMP+timedelta(minutes=i),window_type='regular') for i in range(3)]
        s.create_campaign(campaign,input_text=CSV,config={},planned_start=STAMP,planned_end=STAMP+timedelta(hours=1),
            scheduled_cycles=schedule,source_instruments=[],calendar_version='v1',schedule_version='v1',threshold_version='v1',maintenance_windows=[])
        for i in range(2):
            run = uuid4()
            s.start_run(run,input_text=CSV,config={},image_id='test',campaign_id=campaign)
            if i == 0:
                cycle = uuid4()
                s.start_cycle(cycle,run,market='US',scheduled_at=STAMP,scheduled_cycle_id=schedule[0]['id'])
                s.stop_cycle(cycle,status='skipped',reason='source_cooldown')
            s.finish_run(run)
        with s.report_snapshot():
            data = s.read_campaign(campaign,as_of=STAMP+timedelta(minutes=1))
            assert len(data['runs']) == 2
            rows = data['scheduled_cycles']
            assert [row['due'] for row in rows] == [True,True,False]
            assert rows[0]['cycle_status'] == 'skipped'
            assert rows[1]['cycle_id'] is None and rows[2]['cycle_id'] is None


def test_monitor_campaign_selection_health_and_completion(db):
    cfg, _ = db
    current = datetime.now(UTC)
    with collector(cfg) as s:
        campaign = uuid4()
        schedule = [dict(id=uuid4(),market='US',scheduled_at=current+timedelta(minutes=i),window_type='regular') for i in range(3)]
        s.create_campaign(campaign,input_text=CSV,config={},planned_start=current-timedelta(seconds=1),
            planned_end=current+timedelta(hours=1),scheduled_cycles=schedule,source_instruments=[],
            calendar_version='v1',schedule_version='v1',threshold_version='v1',maintenance_windows=[])
        assert s.find_matching_campaign(input_text=CSV,config={},as_of=current)['id'] == campaign
        assert s.find_matching_campaign(input_text=CSV.replace('2.5','3'),config={},as_of=current) is None
        assert [row['id'] for row in s.scheduled_cycles(campaign,not_before=current+timedelta(seconds=1))] == [row['id'] for row in schedule[1:]]
        run = uuid4()
        s.start_run(run,input_text=CSV,config={},image_id='test',campaign_id=campaign)
        health = s.check_monitor_health(max_age_seconds=10)
        assert health['run_id'] == run and health['age_seconds'] >= 0
        s.interrupt_run(run)
        second = uuid4()
        s.start_run(second,input_text=CSV,config={},image_id='test',campaign_id=campaign)
        s.finish_run(second)
        s.finish_campaign(campaign)
        assert s.get_campaign(campaign)['status'] == 'completed'


def test_provider_cooldown_survives_runner_restart(db):
    cfg, _ = db
    with collector(cfg) as s:
        _, cycle = started(s)
        attempt = uuid4()
        s.start_attempt(attempt,cycle,provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
        failed = FetchResult('us-aapl','yahoo','rate_limited',error='http_429')
        s.finish_attempt(attempt,failed,elapsed_ms=5,
                         provider_evidence={'effective_cooldown_seconds':60,'executed':True})
        remaining = s.provider_cooldowns(as_of=datetime.now(UTC))
        assert 0 < remaining['yahoo'] <= 60


def test_attempt_result_transaction_rolls_back_and_unfinished_blocks_completion(db):
    cfg, admin = db
    with collector(cfg) as s:
        run, cycle = started(s)
        attempt = uuid4()
        s.start_attempt(attempt,cycle,provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
        with pytest.raises(ValueError,match='unfinished'):
            s.finish_cycle(cycle,selected_quotes={})
        # Invalid elapsed duration fails the final UPDATE after quote INSERT.
        with pytest.raises(StorageError):
            s.finish_attempt(attempt,FetchResult('us-aapl','yahoo','success',quote()),elapsed_ms=-1,quote_id=uuid4())
    with Storage(cfg) as reader:
        with reader.report_snapshot():
            data = reader.read_run(run)
            assert data['quotes'] == []
            assert data['fetch_attempts'][0]['status'] == 'started'


def test_readonly_snapshot_is_repeatable_while_writer_commits(db):
    cfg, _ = db
    with collector(cfg) as s, Storage(cfg) as reader:
        run, cycle = started(s)
        with reader.report_snapshot():
            before = reader.read_run(run)
            s.finish_cycle(cycle,selected_quotes={})
            after = reader.read_run(run)
            assert before['cycles'][0]['status'] == after['cycles'][0]['status'] == 'running'
        with reader.report_snapshot():
            assert reader.read_run(run)['cycles'][0]['status'] == 'completed'


def test_timeouts_and_superuser_rejection(db):
    cfg, _ = db
    with collector(replace(cfg,statement_timeout_ms=50)) as s:
        with pytest.raises(StorageError,match='57014'):
            with s.transaction():
                s.conn.execute('SELECT pg_sleep(1)')
    with Storage(replace(cfg,user='postgres',password='stock-poc-isolated-test-only')) as s:
        with pytest.raises(StorageError,match='權限'):
            s.acquire_lock()


def test_duplicate_attempt_rejected_and_missing_table_permission_detected(db):
    cfg, admin = db
    with collector(cfg) as s:
        run, cycle = started(s)
        kwargs = dict(provider='yahoo',instrument_id='us-aapl',ticker='AAPL',attempt_number=1)
        s.start_attempt(uuid4(),cycle,**kwargs)
        with pytest.raises(StorageError,match='23505'):
            s.start_attempt(uuid4(),cycle,**kwargs)
    admin.execute(sql.SQL('ALTER TABLE {}.quotes OWNER TO postgres').format(sql.Identifier(cfg.schema)))
    with Storage(cfg) as s:
        with pytest.raises(StorageError,match='權限'):
            s.check_schema()


def test_connection_failure_redacts_password(db):
    cfg, _ = db
    with pytest.raises(StorageError) as caught:
        with Storage(replace(cfg,password='wrong-private-password')):
            pass
    assert 'wrong-private-password' not in str(caught.value)


def test_catalog_generation_roundtrip_expiration_and_atomic_ambiguity(db):
    from stock_quote_fetcher.catalog import FetchedCatalog, SOURCES
    from stock_quote_fetcher.instruments import CatalogInstrument
    cfg, _ = db
    fetched = []
    for index, spec in enumerate(SOURCES):
        ticker = str(1000+index) if index < 3 else ('AAPL' if index == 3 else 'SPY')
        market = 'TW' if index < 3 else 'US'
        exchange = 'TWSE' if index < 2 else ('TPEx' if index == 2 else 'NASDAQ')
        suffix = '.TW' if exchange == 'TWSE' else ('.TWO' if exchange == 'TPEx' else '')
        entry = CatalogInstrument(f'id:{index}',ticker,market,'TWD' if market=='TW' else 'USD',exchange,
                                  'stock' if ticker not in {'SPY'} else 'etf',f'Name {index}',{'yahoo':ticker+suffix})
        fetched.append(FetchedCatalog(spec.name,STAMP,f'hash-{index}',100,(entry,),False))
    with collector(cfg) as s:
        generation = s.save_instrument_catalog(tuple(fetched),max_age_hours=24)
        stored_generation = s._one('instrument_catalog_generations',generation)
        saved_generation, entries = s.load_instrument_catalog(as_of=stored_generation['completed_at']+timedelta(hours=1))
        assert saved_generation['id'] == generation
        assert len(entries) == 5 and entries[-1].provider_symbols['yahoo'] == 'SPY'
        with pytest.raises(StorageError,match='過期'):
            s.load_instrument_catalog(as_of=stored_generation['completed_at']+timedelta(hours=25))
        duplicate = replace(fetched[-1],entries=(replace(fetched[-1].entries[0],ticker='AAPL',instrument_id='duplicate'),))
        with pytest.raises(ValueError,match='ambiguous'):
            s.save_instrument_catalog(tuple(fetched[:-1])+ (duplicate,),max_age_hours=24)
        count = s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(s.table('instrument_catalog_generations'))).fetchone()['n']
        assert count == 1


def test_quote_runner_persists_comparison_without_switching_and_uses_cache(db):
    from stock_quote_fetcher.config import QuoteConfig
    from stock_quote_fetcher.models import Instrument
    from stock_quote_fetcher.providers import Operation, failure
    from stock_quote_fetcher.quoting import QuoteRunner
    from stock_quote_fetcher.input import parse_holdings
    from stock_quote_fetcher.quality import assess
    cfg,_ = db
    instrument = Instrument('us-aapl','AAPL','US','USD',{'yahoo':'AAPL'},'NASDAQ-Q','stock')
    holdings = parse_holdings(CSV)
    original = assess(replace(quote(),quote_time=datetime(2026,9,4,20,tzinfo=UTC),
                             received_at=datetime(2026,9,7,15,tzinfo=UTC),declared_delay_seconds=0))
    def fetch(i,p,c,t):
        q = replace(original,provider=p,price=Decimal('999') if p == 'finnhub' else original.price)
        return Operation(FetchResult(i.instrument_id,p,'success',q),{'parser_version':'fixture'})
    with collector(cfg) as storage:
        run = uuid4()
        storage.start_run(run,input_text=CSV,config={},image_id='fixture')
        runner = QuoteRunner(storage,QuoteConfig(comparison=('finnhub',)),fetch=fetch)
        reports,_ = runner.run(run,holdings,{'AAPL':instrument},())
        assert reports[0][1].rows[0].market_value == Decimal('500.250')
        assert reports[0][1].rows[0].quote.provider == 'yahoo'
        with storage.report_snapshot():
            saved = storage.read_run(run)
            assert len(saved['fetch_attempts']) == 2 and len(saved['quotes']) == 2
            assert saved['run']['status'] == 'completed'
            assert saved['fetch_attempts'][0]['response_evidence']['adapter']['parser_version'] == 'fixture'
        second = uuid4()
        storage.start_run(second,input_text=CSV,config={},image_id='fixture')
        runner = QuoteRunner(storage,QuoteConfig(),fetch=lambda i,p,c,t:failure(i,p,'provider_error','offline'))
        reports,_ = runner.run(second,holdings,{'AAPL':instrument},())
        row = reports[0][1].rows[0]
        assert row.quote.quote_time == original.quote_time
        assert {'cached','stale'} <= row.quality_flags
        assert reports[0][1].summaries[0].completeness == 'degraded'
        with storage.report_snapshot():
            second_saved = storage.read_run(second)
            assert second_saved['fetch_attempts'][0]['status'] == 'provider_error'
            assert second_saved['valuations'][0]['quote_id'] == saved['valuations'][0]['quote_id']


def test_quote_export_matches_committed_database(db,monkeypatch,tmp_path):
    import json
    import stock_quote_fetcher.quoting as quoting
    from stock_quote_fetcher.instruments import CatalogInstrument
    from stock_quote_fetcher.providers import Operation
    cfg,_ = db
    with collector(cfg):
        pass
    catalog = CatalogInstrument('us-aapl','AAPL','US','USD','NASDAQ-Q','stock','Apple',{'yahoo':'AAPL'},('AAPL',))
    monkeypatch.setattr(quoting,'load_database_config',lambda _:cfg)
    monkeypatch.setattr(Storage,'load_instrument_catalog',lambda self:({'id':uuid4()},(catalog,)))
    monkeypatch.setattr(quoting,'fetch_one',lambda i,p,c,t:Operation(FetchResult(i.instrument_id,p,'success',quote()),{'parser_version':'fixture'}))
    input_path = tmp_path/'input.csv'
    input_path.write_text(CSV)
    config_path = tmp_path/'config.toml'
    config_path.write_text('')
    code,directory,document = quoting.execute(input_path,config_path,tmp_path/'output')
    assert code == 0
    exported = json.loads((directory/'summary.json').read_text())
    assert exported['cycles'][0]['holdings'][0]['market_value'] == '500.250'
    assert list(directory.glob('*/holdings.csv'))
    assert 'test-password' not in (directory/'summary.json').read_text()
    with Storage(cfg) as storage, storage.report_snapshot():
        stored = storage.read_run(document['run_id'])
        assert stored['totals'][0]['total'] == Decimal(exported['cycles'][0]['summaries'][0]['total'])


def test_quote_commit_failure_does_not_export(db,monkeypatch,tmp_path):
    import stock_quote_fetcher.quoting as quoting
    from stock_quote_fetcher.instruments import CatalogInstrument
    from stock_quote_fetcher.providers import Operation
    cfg,_ = db
    with collector(cfg):
        pass
    catalog = CatalogInstrument('us-aapl','AAPL','US','USD','NASDAQ-Q','stock','Apple',{'yahoo':'AAPL'},('AAPL',))
    monkeypatch.setattr(quoting,'load_database_config',lambda _:cfg)
    monkeypatch.setattr(Storage,'load_instrument_catalog',lambda self:({'id':uuid4()},(catalog,)))
    monkeypatch.setattr(quoting,'fetch_one',lambda i,p,c,t:Operation(FetchResult(i.instrument_id,p,'success',quote()),{}))
    original = Storage._insert
    def fail(self,table,record):
        original(self,table,record)
        if table == 'valuation_totals':
            self.conn.execute('SELECT 1/0')
    monkeypatch.setattr(Storage,'_insert',fail)
    input_path,config_path = tmp_path/'input.csv',tmp_path/'config.toml'
    input_path.write_text(CSV)
    config_path.write_text('')
    with pytest.raises(StorageError):
        quoting.execute(input_path,config_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()
    with Storage(cfg) as storage, storage.transaction(writer=False,readonly=True):
        assert storage.conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(storage.table('valuation_totals'))).fetchone()['n'] == 0
        assert storage.conn.execute(sql.SQL('SELECT status FROM {}').format(storage.table('cycles'))).fetchone()['status'] == 'running'


def test_quote_rejects_alias_duplicate_before_fetch(db,monkeypatch,tmp_path):
    import stock_quote_fetcher.quoting as quoting
    from stock_quote_fetcher.instruments import CatalogInstrument
    from stock_quote_fetcher.config import ConfigurationError
    cfg,_ = db
    with collector(cfg):
        pass
    entry = CatalogInstrument('us:nyse:BRK.B','BRK.B','US','USD','NYSE','stock','Berkshire',{'yahoo':'BRK-B'},('BRK.B','BRK-B'))
    monkeypatch.setattr(quoting,'load_database_config',lambda _:cfg)
    monkeypatch.setattr(Storage,'load_instrument_catalog',lambda self:({'id':uuid4()},(entry,)))
    monkeypatch.setattr(quoting,'fetch_one',lambda *a:pytest.fail('duplicate alias reached network'))
    source,config = tmp_path/'input.csv',tmp_path/'config.toml'
    source.write_text('ticker,buy_price,quantity\nBRK.B,1,1\nBRK-B,1,2\n')
    config.write_text('')
    with pytest.raises(ConfigurationError,match='同一標的'):
        quoting.execute(source,config,tmp_path/'out')
    assert not (tmp_path/'out').exists()

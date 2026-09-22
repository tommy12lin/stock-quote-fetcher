"""C5: actual PostgreSQL boundaries plus connection fail-closed tests."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from test_storage import db, collector, started, fetched, quote
from stock_quote_fetcher.cloud_db import bootstrap_sql, capacity, check_runtime, prune
from stock_quote_fetcher.config import DatabaseConfig, QuoteConfig, InstrumentCatalogConfig
from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.quoting import public_config
from stock_quote_fetcher.storage import Storage, StorageError, configuration_snapshot, timeout_ms


def test_tls_config_can_be_snapshotted():
    cfg = DatabaseConfig(password='not-in-snapshot')
    snapshot, _ = configuration_snapshot(public_config(cfg, QuoteConfig(), InstrumentCatalogConfig()))
    assert snapshot['database']['sslmode'] == 'verify-full'
    assert 'password' not in snapshot['database']


@pytest.mark.parametrize('value,expected', [('10s',10000),('3s',3000),('250ms',250),('5min',300000)])
def test_show_units(value, expected):
    assert timeout_ms(value) == expected


@pytest.mark.parametrize('ignored', ['statement_timeout','lock_timeout','TimeZone','search_path'])
def test_ignored_session_settings_close_connection(monkeypatch, ignored):
    class Connection:
        closed = False
        def execute(self, query):
            text = query.as_string() if hasattr(query,'as_string') else query
            if text.startswith('SHOW'):
                name=text.split('"')[1]
                expected={'statement_timeout':'10s','lock_timeout':'3s','TimeZone':'UTC','search_path':'pg_catalog'}
                values=expected | {ignored: {'statement_timeout':'2min','lock_timeout':'0','TimeZone':'Asia/Taipei','search_path':'public'}[ignored]}
                self.result={name:values[name]}
            return self
        def fetchone(self): return self.result
        def close(self): self.closed=True
    conn=Connection()
    monkeypatch.setattr(psycopg,'connect',lambda **kwargs: conn)
    with pytest.raises(StorageError,match='未生效'):
        with Storage(DatabaseConfig(password='test')): pass
    assert conn.closed


def test_session_timeouts_actually_cancel(db):
    cfg, _ = db
    cfg=replace(cfg,statement_timeout_ms=250,lock_timeout_ms=100)
    with Storage(cfg) as a, Storage(cfg) as b:
        with pytest.raises(psycopg.errors.QueryCanceled): a.conn.execute('SELECT pg_sleep(1)')
        a.conn.execute('SELECT pg_advisory_lock(837264)')
        try:
            with pytest.raises(psycopg.errors.LockNotAvailable): b.conn.execute('SELECT pg_advisory_lock(837264)')
        finally: a.conn.execute('SELECT pg_advisory_unlock(837264)')
        assert a.conn.execute('SELECT 1 AS ok').fetchone()['ok']==1


def test_bootstrap_and_runtime_privileges(db):
    cfg, admin = db
    statement=bootstrap_sql(cfg.schema,cfg.user)
    admin.execute(statement)
    admin.execute(statement)  # idempotent
    with admin.transaction(force_rollback=True):
        admin.execute('SET LOCAL ROLE pg_read_all_data')
        # Even a role with table read privileges sees no rows without a runtime policy.
        assert admin.execute(sql.SQL('SELECT count(*) FROM {}.portfolio').format(sql.Identifier(cfg.schema))).fetchone()[0] == 0
    with Storage(cfg) as s:
        assert check_runtime(s)=={'runtime_permissions':'passed'}
        assert s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(s.table('portfolio'))).fetchone()['n']==1
        with s.conn.transaction(force_rollback=True):
            s.conn.execute(sql.SQL("INSERT INTO {} VALUES ('c5-test','{{}}')").format(s.table('refresh_jobs')))
            s.conn.execute(sql.SQL("UPDATE {} SET document='{{\"status\":\"succeeded\"}}' WHERE id='c5-test'").format(s.table('refresh_jobs')))
            assert s.conn.execute(sql.SQL("SELECT document FROM {} WHERE id='c5-test'").format(s.table('refresh_jobs'))).fetchone()['document']['status']=='succeeded'
        for statement in [sql.SQL('CREATE TABLE {} (id int)').format(s.table('forbidden')),sql.SQL('DELETE FROM {} WHERE false').format(s.table('portfolio')),sql.SQL("UPDATE {} SET checksum='bad' WHERE false").format(s.table('schema_migrations'))]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege): s.conn.execute(statement)
        assert capacity(s)['schema_bytes']>0
        assert all(row['index_bytes']>0 for row in capacity(s)['tables'])
        with pytest.raises(psycopg.errors.InsufficientPrivilege): prune(s,apply=True)


def test_bootstrap_rejects_migration_tampering_atomically(db):
    cfg, admin=db
    admin.execute(bootstrap_sql(cfg.schema,cfg.user))
    admin.execute(sql.SQL("UPDATE {}.schema_migrations SET checksum='changed' WHERE version='0001_initial.sql'").format(sql.Identifier(cfg.schema)))
    with pytest.raises(psycopg.errors.RaiseException): admin.execute(bootstrap_sql(cfg.schema,cfg.user))
    admin.execute('ROLLBACK')


def test_prune_preserves_cache_dependencies_jobs_and_catalog(db):
    cfg, admin = db
    service=Dashboard.__new__(Dashboard);service.db=cfg;service.initialize()
    old=datetime.now(UTC)-timedelta(days=90)
    runs=[]; cycles=[]; quotes=[]
    with collector(cfg) as s:
        for i in range(24):
            run,cycle=started(s)
            _,qid=fetched(s,cycle,replace(quote(),received_at=old+timedelta(seconds=i)))
            s.finish_cycle(cycle,selected_quotes={'AAPL':qid});s.finish_run(run)
            runs.append(run);cycles.append(cycle);quotes.append(qid)
        orphan,_cycle=started(s);s.stop_cycle(_cycle,status='interrupted',reason='test');s.interrupt_run(orphan)
        s.conn.execute(sql.SQL('UPDATE {} SET ended_at=%s').format(s.table('runs')),(old,))
        # Retained latest run references oldest quote, which itself references another run.
        s.conn.execute(sql.SQL('UPDATE {} SET quote_id=%s WHERE run_id=%s').format(s.table('valuations')),(quotes[0],runs[-1]))
        s.conn.execute(sql.SQL('UPDATE {} SET quote_id=%s WHERE run_id=%s').format(s.table('valuations')),(quotes[1],runs[0]))
        active,_=started(s)
        for i in range(4):
            s.conn.execute(sql.SQL("INSERT INTO {} VALUES (%s,%s,%s,%s,'[]')").format(s.table('instrument_catalog_generations')),(uuid4(),old,old+timedelta(seconds=i),old+timedelta(days=1)))
    for i,status in enumerate(['succeeded','failed','running','queued']):
        service.put_job({'job_id':str(i),'status':status,'created_at':(old+timedelta(seconds=i)).isoformat(),'completed_at':old.isoformat()})
    with Storage(cfg) as s:
        before=capacity(s)
        result=prune(s)
        assert result['runs']==3 and result['catalog_generations']==2 and result['jobs']==2
        assert s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(s.table('runs'))).fetchone()['n']==26
        assert prune(s,apply=True)==result|{'apply':True}
        remaining={r['id'] for r in s.conn.execute(sql.SQL('SELECT id FROM {}').format(s.table('runs')))}
        assert set(runs)-{runs[2],runs[3]} <= remaining and active in remaining and orphan not in remaining
        assert service.get()['revision']==0
        assert prune(s)['runs']==prune(s)['jobs']==prune(s)['catalog_generations']==0
        assert before['schema_bytes']>0 and sum(r['index_bytes'] for r in before['tables'])>0
        print('C5 fixture capacity:', before['schema_bytes'],'table bytes:',sum(r['table_bytes'] for r in before['tables']),'index bytes:',sum(r['index_bytes'] for r in before['tables']))


def test_prune_refuses_active_collector(db):
    cfg,_=db
    service=Dashboard.__new__(Dashboard);service.db=cfg;service.initialize()
    with collector(cfg), Storage(cfg) as maintenance:
        with pytest.raises(StorageError,match='正在執行'): prune(maintenance,apply=True)


def test_dashboard_never_falls_back_to_source(monkeypatch,tmp_path):
    cfg=tmp_path/'single.toml';cfg.write_text('[database]\nschema="dashboard"\n')
    monkeypatch.setenv('DB_PASSWORD','test')
    service=Dashboard(cfg)
    seen=[]
    class MissingCatalog:
        def __init__(self, config): seen.append(config.schema)
        def __enter__(self): raise StorageError('no catalog')
        def __exit__(self,*args): pass
    monkeypatch.setattr('stock_quote_fetcher.dashboard.Storage',MissingCatalog)
    from stock_quote_fetcher.web_input import WebError
    with pytest.raises(WebError): service.catalog()
    assert seen==['dashboard']

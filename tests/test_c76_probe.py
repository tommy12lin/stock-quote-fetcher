"""C7-6 R0 rehearsal: the probe's rounds, end to end through main(), then purged.

The network is faked (official listing and Yahoo); everything else is the real path on
the disposable database. What this cannot show is anything about the real sources.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
import json
from uuid import UUID

from psycopg import sql
import pytest

from test_storage import db, collector, STAMP
from test_cloud_db import measured, owned
from scripts.c76_probe import FIXED, main, select_wide, tickers_for
from stock_quote_fetcher import quoting
from stock_quote_fetcher.cloud_db import RUN_TABLES, purge
from stock_quote_fetcher.instruments import CatalogInstrument
from stock_quote_fetcher.models import FetchResult, Quote
from stock_quote_fetcher.providers import Operation
from stock_quote_fetcher.storage import Storage


def entry(index, ticker, market, exchange, asset_type):
    suffix = {'TWSE': '.TW', 'TPEx': '.TWO'}.get(exchange, '')
    return CatalogInstrument(f'id:{index}', ticker, market, 'TWD' if market == 'TW' else 'USD', exchange,
                             asset_type, f'Name {index}', {'yahoo': ticker + suffix})


def official_listing(config):
    """One entry per official source, the shape catalog.fetch_all returns."""
    from stock_quote_fetcher.catalog import FetchedCatalog, SOURCES
    rows = [entry(0, '1101', 'TW', 'TWSE', 'stock'), entry(1, '0050', 'TW', 'TWSE', 'etf'),
            entry(2, '6488', 'TW', 'TPEx', 'stock'), entry(3, 'AAPL', 'US', 'NASDAQ', 'stock'),
            entry(4, 'SPY', 'US', 'NYSE Arca', 'etf')]
    return tuple(FetchedCatalog(spec.name, STAMP, f'hash-{i}', 100, (row,), False)
                 for i, (spec, row) in enumerate(zip(SOURCES, rows)))


def yahoo(instrument, provider, config, timeout):
    stamp = datetime.now(UTC)
    q = Quote(instrument.instrument_id, instrument.ticker, instrument.provider_symbols['yahoo'], instrument.market,
              instrument.currency, provider, Decimal('10'), 'last_trade', stamp, stamp, None, 'regular', 'second')
    return Operation(FetchResult(instrument.instrument_id, provider, 'success', q), {'parser_version': 'fixture'})


@pytest.fixture
def probe(db, tmp_path, monkeypatch):
    cfg, _ = db
    path = tmp_path / 'probe.toml'
    path.write_text(f'[database]\nhost="{cfg.host}"\nname="{cfg.name}"\nuser="{cfg.user}"\n'
                    'sslmode="disable"\nsslrootcert=""\n', encoding='utf-8')
    monkeypatch.setenv('DB_PASSWORD', cfg.password)
    monkeypatch.setattr('stock_quote_fetcher.catalog.fetch_all', official_listing)
    monkeypatch.setattr(quoting, 'fetch_one', yahoo)
    from stock_quote_fetcher.dashboard import Dashboard
    service = Dashboard(path, cfg.schema)
    service.initialize()

    def run(mode, **env):
        out = StringIO()
        code = main({'C76_MODE': mode, 'C76_CONFIG': str(path), 'C76_SCHEMA': cfg.schema, **env}, out)
        lines = out.getvalue().splitlines()
        assert all(line.startswith('C76 ') for line in lines)
        return code, [json.loads(line[4:]) for line in lines]
    return cfg, service, run


def one(records, kind):
    found = [r for r in records if r['kind'] == kind]
    assert len(found) == 1, (kind, found)
    return found[0]


def age_jobs(cfg):
    """C4-5 holds refreshes 60 s apart; the Job's rounds are hours apart, a test's are not."""
    with Storage(cfg) as s:
        s.conn.execute(sql.SQL("UPDATE {} SET document=jsonb_set(document,'{{created_at}}',to_jsonb(%s::text))").format(
            s.table('refresh_jobs')), ((datetime.now(UTC) - timedelta(minutes=5)).isoformat(),))


def test_wide_selection_is_reproducible_and_split_by_market():
    listing = official_listing(None)
    entries = tuple(e for fetched in listing for e in fetched.entries)
    assert select_wide(entries, 4) == select_wide(tuple(reversed(entries)), 4)
    assert sorted(t for t in select_wide(entries, 4) if t in {'AAPL', 'SPY'}) == ['AAPL', 'SPY']
    assert tickers_for('fixed', entries) == FIXED and len(FIXED) == 11
    for spec in ('wide:1', 'wide:501', 'wide:x', 'many'):
        with pytest.raises(ValueError): tickers_for(spec, entries)
    with pytest.raises(ValueError, match='不足'): select_wide(entries, 8)


def test_rounds_leave_a_manifest_that_purges_exactly_what_they_wrote(probe):
    cfg, service, run = probe
    with collector(cfg) as s:
        neighbour, _ = measured(s)  # written before the probe; its diff must not claim it

    code, r1 = run('catalog')
    assert code == 0 and one(r1, 'job')['status'] == 'succeeded' and one(r1, 'catalog')['instruments'] == 5
    first = one(r1, 'manifest')
    assert first['runs'] == [] and first['refresh_jobs'] == [one(r1, 'job')['job_id']]

    age_jobs(cfg)
    code, r2 = run('refresh', C76_TICKERS='wide:4')
    assert code == 0, r2
    second = one(r2, 'manifest')
    with Storage(cfg) as s:
        everything = {str(r['id']) for r in s.conn.execute(sql.SQL('SELECT id FROM {}').format(s.table('runs')))}
    assert set(second['runs']) == everything - {str(neighbour)} and second['runs']
    assert len([r for r in r2 if r['kind'] == 'attempt']) == 4
    assert all(r['status'] == 'success' and r['price'] for r in r2 if r['kind'] == 'attempt')
    assert len([r for r in r2 if r['kind'] == 'view']) == 4
    assert sum(r['tickers'] for r in r2 if r['kind'] == 'batch') == 4
    revision = one(r2, 'portfolio')['revision']

    # A reset against a revision someone has since moved past is refused, not applied.
    code, stale = run('reset', C76_EXPECT_REVISION=str(revision - 1))
    assert code == 1 and one(stale, 'error')['status'] == 409 and service.get()['rows']
    code, r3 = run('reset', C76_EXPECT_REVISION=str(revision))
    assert code == 0 and service.get()['rows'] == [] and service.get()['revision'] == one(r3, 'reset')['revision']

    runs = sorted(UUID(r) for r in second['runs'])
    jobs = first['refresh_jobs'] + second['refresh_jobs']
    with Storage(cfg) as s:
        purge(s, runs=runs, jobs=jobs, apply=True)
        assert not any(owned(s, runs).values())
        assert owned(s, [neighbour]) == dict.fromkeys(RUN_TABLES, 1)
        assert s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(s.table('refresh_jobs'))).fetchone()['n'] == 0
    # The listing is official data, kept on purpose (C7-6 decision of 2026-09-23).
    assert len(service.catalog()) == 5


def test_bad_input_is_reported_as_a_line_not_a_traceback(probe):
    cfg, service, run = probe
    assert run('nonsense')[0] == 2
    assert run('reset')[0] == 2
    run('catalog')
    age_jobs(cfg)
    code, records = run('refresh', C76_TICKERS='wide:99')
    assert code == 2 and '不足' in one(records, 'error')['message']
    assert not [r for r in records if r['kind'] == 'manifest'] and service.get()['rows'] == []

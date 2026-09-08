from datetime import UTC, datetime, timedelta
import json
import os
import signal
import sys
from threading import Event
from uuid import UUID, uuid4

import pytest
from psycopg import sql

from stock_quote_fetcher.config import ConfigurationError, QuoteConfig, load_quote_config
from stock_quote_fetcher.models import FetchResult, Market
from stock_quote_fetcher.storage import Storage, StorageError
import stock_quote_fetcher.monitor as monitor
from stock_quote_fetcher.monitor import build_schedule
from test_storage import CSV, collector, db, quote, started  # noqa: F401  (shared disposable fixture)


def first_for(market, start, end, config=None):
    rows = build_schedule({market}, start, end, config or QuoteConfig())
    return rows[0]["scheduled_at"], rows


def test_schedule_uses_market_holidays_and_independent_markets():
    # 2026-09-07 is a US holiday but a TW trading day.
    start = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
    rows = build_schedule({Market.TW, Market.US}, start, end, QuoteConfig(poll_interval_seconds=3600))
    us = [row for row in rows if row["market"] == "US"]
    tw = [row for row in rows if row["market"] == "TW"]
    assert tw and us
    assert all(row["scheduled_at"].date().isoformat() != "2026-09-07" for row in us)


def test_schedule_handles_dst_early_close_and_opening_delay():
    config = QuoteConfig(poll_interval_seconds=3600)
    before, _ = first_for(Market.US, datetime(2026,3,6,0,tzinfo=UTC), datetime(2026,3,7,0,tzinfo=UTC), config)
    after, _ = first_for(Market.US, datetime(2026,3,9,0,tzinfo=UTC), datetime(2026,3,10,0,tzinfo=UTC), config)
    assert before.hour == 14 and after.hour == 13
    _, early = first_for(Market.US, datetime(2026,11,27,0,tzinfo=UTC), datetime(2026,11,28,0,tzinfo=UTC), config)
    regular = [row for row in early if row["window_type"] == "regular"]
    assert max(row["scheduled_at"] for row in regular).hour < 19
    tw_config = QuoteConfig(poll_interval_seconds=60)
    _, tw = first_for(Market.TW, datetime(2026,9,8,0,tzinfo=UTC), datetime(2026,9,8,2,tzinfo=UTC), tw_config)
    opening = [row for row in tw if row["window_type"] == "opening_delay"]
    assert len(opening) == 20


def test_monitor_scheduler_config_is_validated_and_loaded(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("""[scheduler]
campaign_duration_days=3
post_close_observation_minutes=45
heartbeat_interval_seconds=20
""")
    config = load_quote_config(path)
    assert (config.campaign_duration_days, config.post_close_observation_minutes,
            config.heartbeat_interval_seconds) == (3,45,20)
    for kwargs in ({"campaign_duration_days":0},{"post_close_observation_minutes":0},
                   {"heartbeat_interval_seconds":True}):
        with pytest.raises(ConfigurationError):
            QuoteConfig(**kwargs)


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX signal delivery')
def test_stop_signals_request_a_cooperative_stop_and_restore_handlers():
    event = Event()
    previous = {name: signal.getsignal(getattr(signal, name)) for name in ('SIGTERM', 'SIGINT')}
    with monitor.stop_signals(event):
        os.kill(os.getpid(), signal.SIGTERM)
        for _ in range(1000):                  # Handlers run between bytecodes, not instantly.
            if event.is_set():
                break
    assert event.is_set()
    assert all(signal.getsignal(getattr(signal, name)) is handler for name, handler in previous.items())


class Clock:
    """Deterministic campaign clock; wait_fn advances it and can inject lag or a stop."""

    def __init__(self, start, *, stop=None, lag_after=None, stop_after=None):
        self.now, self.calls = start, 0
        self.stop, self.lag_after, self.stop_after = stop, lag_after, stop_after

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.calls += 1
        self.now += timedelta(seconds=seconds)
        if self.calls == self.lag_after:
            self.now += timedelta(hours=2)
        if self.calls == self.stop_after:
            self.stop.set()
        return False


SESSION_OPEN = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
SCHEDULER = '[scheduler]\npoll_interval_seconds=3600\ncampaign_duration_days=1\nheartbeat_interval_seconds=300\n'


def campaign_files(tmp_path):
    source, config = tmp_path / 'input.csv', tmp_path / 'config.toml'
    source.write_text(CSV)
    config.write_text(SCHEDULER)
    return source, config


def offline_monitor(monkeypatch, cfg):
    """Bind monitor to the disposable database and to a fixed catalog and quote."""
    from stock_quote_fetcher.instruments import CatalogInstrument
    from stock_quote_fetcher.providers import Operation
    catalog = CatalogInstrument('us-aapl','AAPL','US','USD','NASDAQ-Q','stock','Apple',{'yahoo':'AAPL'},('AAPL',))
    monkeypatch.setattr(monitor, 'load_database_config', lambda _: cfg)
    monkeypatch.setattr(Storage, 'load_instrument_catalog', lambda self, **_: ({'id': uuid4()}, (catalog,)))
    return lambda instrument, provider, config, timeout: Operation(
        FetchResult(instrument.instrument_id, provider, 'success', quote()), {'parser_version': 'fixture'})


def run_campaign(source, config, output, *, clock, stop, fetch, campaign_id=None):
    return monitor.execute(source, config, output, campaign_id=campaign_id, stop_event=stop,
                           now_fn=clock, wait_fn=clock.wait, fetch=fetch,
                           monotonic=lambda: 0, sleep=lambda _: None)


def runs_in(cfg):
    with Storage(cfg) as storage, storage.transaction(writer=False, readonly=True):
        return storage.conn.execute(sql.SQL('SELECT id,status,campaign_id FROM {} ORDER BY started_at').format(
            storage.table('runs'))).fetchall()


def test_monitor_stop_resumes_same_campaign_and_skips_late_cycles(db, monkeypatch, tmp_path):
    cfg, _ = db
    with collector(cfg):
        pass
    fetch = offline_monitor(monkeypatch, cfg)
    source, config = campaign_files(tmp_path)
    stop = Event()
    clock = Clock(SESSION_OPEN, stop=stop, lag_after=1, stop_after=2)
    code, directory, first = run_campaign(source, config, tmp_path/'output', clock=clock, stop=stop, fetch=fetch)

    assert code == 0 and first['status'] == 'interrupted' and first['campaign_created'] is True
    assert [(row['status'], row.get('reason')) for row in first['cycles']] == [
        ('completed', None), ('skipped', 'scheduler_lag'), ('completed', None)]
    assert json.loads((directory/'summary.json').read_text())['status'] == 'interrupted'

    stop = Event()
    resumed = Clock(SESSION_OPEN + timedelta(seconds=9000), stop=stop, stop_after=7)
    _, _, second = run_campaign(source, config, tmp_path/'output', clock=resumed, stop=stop, fetch=fetch)

    # A restart keeps the campaign and its remaining opportunities, under a new run-id.
    assert second['campaign_created'] is False and second['campaign_id'] == first['campaign_id']
    assert second['run_id'] != first['run_id'] and second['status'] == 'interrupted'
    assert [row['status'] for row in second['cycles']] == ['completed']
    assert second['cycles'][0]['scheduled_at'] == (SESSION_OPEN + timedelta(seconds=10800)).isoformat()

    runs = runs_in(cfg)
    assert [row['status'] for row in runs] == ['interrupted', 'interrupted']
    assert {str(row['campaign_id']) for row in runs} == {first['campaign_id']}
    with Storage(cfg) as storage:
        assert storage.get_campaign(UUID(first['campaign_id']))['status'] == 'running'
        # No opportunity is claimed twice, and every cycle points at a scheduled one.
        with storage.transaction(writer=False, readonly=True):
            claimed = storage.conn.execute(sql.SQL('SELECT scheduled_cycle_id FROM {}').format(
                storage.table('cycles'))).fetchall()
    identifiers = [row['scheduled_cycle_id'] for row in claimed]
    assert len(identifiers) == 4 and all(identifiers) and len(set(identifiers)) == 4


def test_monitor_recovers_unexpected_stop_and_healthcheck_needs_a_live_run(db, monkeypatch, tmp_path):
    cfg, admin = db
    with collector(cfg) as storage:
        crashed, _ = started(storage)          # Left running, as an unexpected stop would.
    admin.execute(sql.SQL("UPDATE {} SET heartbeat_at=now()-interval '10 minutes'").format(
        sql.Identifier(cfg.schema, 'runs')))
    with Storage(cfg) as storage:
        # A crashed process keeps its row running, so staleness is what healthcheck must catch.
        with pytest.raises(StorageError, match='心跳已逾期'):
            storage.check_monitor_health(max_age_seconds=60)

    fetch = offline_monitor(monkeypatch, cfg)
    source, config = campaign_files(tmp_path)
    stop = Event()
    clock = Clock(SESSION_OPEN - timedelta(seconds=60), stop=stop, stop_after=1)
    _, _, document = run_campaign(source, config, tmp_path/'output', clock=clock, stop=stop, fetch=fetch)

    assert document['recovered'] == {'fetch_attempts': 0, 'cycles': 1, 'runs': 1}
    assert document['cycles'] == [] and document['status'] == 'interrupted'
    assert UUID(document['run_id']) != crashed
    assert [row['status'] for row in runs_in(cfg)] == ['interrupted', 'interrupted']
    with Storage(cfg) as storage:
        with pytest.raises(StorageError, match='沒有進行中的 run'):
            storage.check_monitor_health(max_age_seconds=60)


def test_monitor_rejects_unknown_or_closed_campaign(db, monkeypatch, tmp_path):
    cfg, _ = db
    with collector(cfg):
        pass
    fetch = offline_monitor(monkeypatch, cfg)
    source, config = campaign_files(tmp_path)
    stop = Event()
    for identity, message in ((uuid4(), '不存在'), ('not-a-uuid', '有效 UUID')):
        with pytest.raises(ConfigurationError, match=message):
            run_campaign(source, config, tmp_path/'rejected', stop=stop, fetch=fetch,
                         clock=Clock(SESSION_OPEN, stop=stop, stop_after=1), campaign_id=identity)
    _, _, document = run_campaign(source, config, tmp_path/'output', stop=stop, fetch=fetch,
                                  clock=Clock(SESSION_OPEN, stop=stop, stop_after=1))
    campaign = UUID(document['campaign_id'])
    with Storage(cfg) as storage:
        storage.acquire_lock()
        storage.finish_campaign(campaign)
    stop = Event()
    with pytest.raises(ConfigurationError, match='可續跑期間'):
        run_campaign(source, config, tmp_path/'closed', stop=stop, fetch=fetch,
                     clock=Clock(SESSION_OPEN, stop=stop, stop_after=1), campaign_id=campaign)

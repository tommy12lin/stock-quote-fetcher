"""Calendar scheduler and recoverable monitor campaign orchestration."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import csv
import json
from importlib.metadata import version
import math
from pathlib import Path
import signal
from threading import Event
from uuid import UUID, uuid4

from stock_quote_fetcher.config import (
    ConfigurationError,
    load_database_config,
    load_instrument_catalog_config,
    load_quote_config,
)
from stock_quote_fetcher.input import parse_holdings
from stock_quote_fetcher.instruments import resolve_holdings
from stock_quote_fetcher.models import Market
from stock_quote_fetcher.providers import applicable
from stock_quote_fetcher.quality import calendar, timezone
from stock_quote_fetcher.quoting import CollectionInterrupted, QuoteRunner, public_config
from stock_quote_fetcher.storage import Storage


SCHEDULE_VERSION = "monitor-v1"
THRESHOLD_VERSION = "unconfirmed-v1"


def utc_now():
    return datetime.now(UTC)


def _post_close_seconds(market, providers, config):
    # Yahoo declares 20 minutes for TW and zero for US. Official TW close files and
    # Finnhub have no confirmed publication/delay contract, so use the configured cap.
    known_delay = 1200 if market == Market.TW else 0
    unknown = ((market == Market.TW and set(providers) & {"twse", "tpex"})
               or (market == Market.US and "finnhub" in providers))
    if unknown:
        return config.post_close_observation_minutes * 60
    return known_delay + 2 * config.poll_interval_seconds


def build_schedule(markets, planned_start, planned_end, config):
    """Expand immutable, independent market opportunities using exchange calendars."""
    if planned_start.tzinfo is None or planned_end.tzinfo is None or planned_end <= planned_start:
        raise ValueError("Campaign times must be timezone-aware and increasing.")
    start, end = planned_start.astimezone(UTC), planned_end.astimezone(UTC)
    providers = (config.valuation, *config.comparison)
    interval = timedelta(seconds=config.poll_interval_seconds)
    result = []
    for market in sorted({Market(item) for item in markets}, key=lambda item: item.value):
        local = timezone(market)
        first_day = (start.astimezone(local) - timedelta(days=1)).date()
        last_day = end.astimezone(local).date()
        cal = calendar(market, first_day.year)
        sessions = cal.sessions_in_range(str(first_day), str(last_day))
        opening_delay = timedelta(minutes=20 if market == Market.TW else 0)
        post_close = timedelta(seconds=_post_close_seconds(market, providers, config))
        for label in sessions:
            opening, closing = (stamp.to_pydatetime().astimezone(UTC)
                                for stamp in cal.session_open_close(label))
            window_start = max(start, opening)
            window_end = min(end, closing + post_close)
            if window_start >= window_end:
                continue
            elapsed = max(0, (window_start - opening).total_seconds())
            tick = opening + interval * math.ceil(elapsed / interval.total_seconds())
            while tick < window_end:
                if tick <= closing:
                    window_type = "opening_delay" if tick < opening + opening_delay else "regular"
                else:
                    window_type = "post_close"
                result.append({"id": uuid4(), "market": market.value,
                               "scheduled_at": tick, "window_type": window_type})
                tick += interval
    return sorted(result, key=lambda row: (row["scheduled_at"], row["market"], str(row["id"])))


def source_instruments(resolved, config):
    rows = []
    for instrument in sorted(resolved.values(), key=lambda item: (item.market.value, item.ticker)):
        for provider in (config.valuation, *config.comparison):
            if applicable(instrument, provider):
                rows.append({"provider": provider, "instrument_id": instrument.instrument_id,
                             "ticker": instrument.ticker, "market": instrument.market.value})
    return rows


def _write_summary(directory: Path, document):
    target = directory / "summary.json"
    temporary = directory / "summary.json.tmp"
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def _write_cycle(directory: Path, cycle, report):
    data = report.to_dict()
    target = directory / str(cycle)
    target.mkdir()
    with (target / "holdings.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data["holdings"][0]))
        writer.writeheader()
        for row in data["holdings"]:
            writer.writerow({**row, "quality_flags": "|".join(row["quality_flags"])})
    return data


def _wait_until(target, *, run_id, storage, config, stop_event, now_fn, wait_fn):
    while not stop_event.is_set():
        remaining = (target - now_fn()).total_seconds()
        if remaining <= 0:
            return True
        storage.heartbeat(run_id)
        wait_fn(min(remaining, config.heartbeat_interval_seconds))
    return False


def execute(input_path, config_path, output_path, *, campaign_id=None, stop_event=None,
            now_fn=utc_now, wait_fn=None, fetch=None, monotonic=None, sleep=None):
    """Run or resume a finite campaign. Graceful stop leaves it resumable."""
    try:
        text = input_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise ConfigurationError("無法讀取持股 CSV；請核對路徑、權限與 UTF-8 編碼。") from None
    holdings = parse_holdings(text)
    database = load_database_config(config_path)
    quote = load_quote_config(config_path)
    catalog_config = load_instrument_catalog_config(config_path)
    public = public_config(database, quote, catalog_config)
    if campaign_id is not None:
        try:
            campaign_id = UUID(str(campaign_id))
        except ValueError:
            raise ConfigurationError("--campaign-id 必須是有效 UUID。") from None
    stop_event = stop_event or Event()
    wait_fn = wait_fn or stop_event.wait
    run_id = uuid4()
    started = now_fn().astimezone(UTC)
    directory = output_path / str(run_id)
    document = {"run_id": str(run_id), "campaign_id": None, "status": "starting",
                "started_at": started.isoformat(), "cycles": [], "attempts": [],
                "comparisons": [], "recovered": {}}
    with Storage(database) as storage:
        storage.acquire_lock()
        storage.check_schema()
        generation, entries = storage.load_instrument_catalog(as_of=started)
        resolved, issues = resolve_holdings(holdings, entries)
        if len({item.instrument_id for item in resolved.values()}) != len(resolved):
            raise ConfigurationError("多個輸入代碼對應同一標的；請合併持股並保留一種代碼。")
        recovered = storage.recover_incomplete()
        document["recovered"] = recovered
        if campaign_id is None:
            campaign = storage.find_matching_campaign(input_text=text, config=public, as_of=started)
            if campaign is None:
                campaign_id = uuid4()
                planned_end = started + timedelta(days=quote.campaign_duration_days)
                schedule = build_schedule({holding.market for holding in holdings}, started, planned_end, quote)
                storage.create_campaign(
                    campaign_id, input_text=text, config=public, planned_start=started,
                    planned_end=planned_end, scheduled_cycles=schedule,
                    source_instruments=source_instruments(resolved, quote),
                    calendar_version=f"exchange-calendars/{version('exchange-calendars')}",
                    schedule_version=SCHEDULE_VERSION, threshold_version=THRESHOLD_VERSION,
                    maintenance_windows=[])
                campaign = storage.get_campaign(campaign_id)
                document["campaign_created"] = True
            else:
                campaign_id = campaign["id"]
                document["campaign_created"] = False
        else:
            try:
                campaign = storage.get_campaign(campaign_id)
            except ValueError:
                raise ConfigurationError("指定的 campaign 不存在。") from None
            if campaign["status"] != "running" or not campaign["planned_start"] <= started < campaign["planned_end"]:
                raise ConfigurationError("指定的 campaign 未在可續跑期間內。")
            document["campaign_created"] = False
        try:
            storage.start_run(run_id, input_text=text, config=public, image_id="runtime-unspecified",
                              campaign_id=campaign_id)
        except ValueError as exc:
            raise ConfigurationError("指定 campaign 的輸入或公開設定不一致。") from exc
        document.update(campaign_id=str(campaign_id), catalog_generation=str(generation["id"]),
                        planned_start=campaign["planned_start"].isoformat(),
                        planned_end=campaign["planned_end"].isoformat(), status="running")
        try:
            directory.mkdir(parents=True, exist_ok=False)
            _write_summary(directory, document)
            runner_args = {"stop_requested": stop_event.is_set}
            if fetch is not None:
                runner_args["fetch"] = fetch
            if monotonic is not None:
                runner_args["monotonic"] = monotonic
            if sleep is not None:
                runner_args["sleep"] = sleep
            runner = QuoteRunner(storage, quote, **runner_args)
            runner.restore_cooldowns(storage.provider_cooldowns(as_of=started))
            opportunities = storage.scheduled_cycles(campaign_id, not_before=started)
            for opportunity in opportunities:
                scheduled_at = opportunity["scheduled_at"]
                if not _wait_until(scheduled_at, run_id=run_id, storage=storage, config=quote,
                                   stop_event=stop_event, now_fn=now_fn, wait_fn=wait_fn):
                    break
                if stop_event.is_set():
                    break
                late_by = (now_fn().astimezone(UTC) - scheduled_at).total_seconds()
                if late_by >= quote.poll_interval_seconds:
                    cycle = uuid4()
                    storage.start_cycle(cycle, run_id, market=opportunity["market"],
                                        scheduled_at=scheduled_at, scheduled_cycle_id=opportunity["id"])
                    storage.stop_cycle(cycle, status="skipped", reason="scheduler_lag")
                    document["cycles"].append({"cycle_id": str(cycle), "market": opportunity["market"],
                                               "scheduled_at": scheduled_at.isoformat(), "status": "skipped",
                                               "reason": "scheduler_lag"})
                    _write_summary(directory, document)
                    continue
                cycle, report, comparisons, events = runner.run_cycle(
                    run_id, holdings, resolved, issues, market=Market(opportunity["market"]),
                    scheduled_at=scheduled_at, scheduled_cycle_id=opportunity["id"])
                data = _write_cycle(directory, cycle, report)
                document["cycles"].append({"cycle_id": str(cycle), "market": opportunity["market"],
                                           "scheduled_at": scheduled_at.isoformat(), "status": "completed", **data})
                document["attempts"].extend(events)
                document["comparisons"].extend(comparisons)
                storage.heartbeat(run_id)
                _write_summary(directory, document)
            if stop_event.is_set():
                storage.interrupt_run(run_id)
                document["status"] = "interrupted"
            else:
                _wait_until(campaign["planned_end"], run_id=run_id, storage=storage, config=quote,
                            stop_event=stop_event, now_fn=now_fn, wait_fn=wait_fn)
                if stop_event.is_set():
                    storage.interrupt_run(run_id)
                    document["status"] = "interrupted"
                else:
                    storage.finish_run(run_id)
                    storage.finish_campaign(campaign_id)
                    document["status"] = "completed"
            document["ended_at"] = now_fn().astimezone(UTC).isoformat()
            _write_summary(directory, document)
            return 0, directory, document
        except CollectionInterrupted:
            if not storage.failed:
                storage.interrupt_run(run_id)
                document.update(status="interrupted", ended_at=now_fn().astimezone(UTC).isoformat())
                _write_summary(directory, document)
            return 0, directory, document
        except BaseException:
            if not storage.failed:
                try:
                    storage.interrupt_run(run_id)
                except (ValueError, RuntimeError):
                    pass
            raise


@contextmanager
def stop_signals(event):
    """Translate SIGTERM/SIGINT into a cooperative stop flag and restore handlers."""
    previous = {}
    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is not None:
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda *_: event.set())
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

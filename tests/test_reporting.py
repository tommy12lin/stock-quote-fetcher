"""Report metrics on a hand-checkable fixed observation record; no fetching, no clock guessing."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
from threading import Event
from uuid import uuid4

import pytest

from stock_quote_fetcher.config import ConfigurationError
from stock_quote_fetcher.storage import Storage, StorageError
import stock_quote_fetcher.reporting as reporting
from stock_quote_fetcher.reporting import build_campaign, build_run, percentile, run_schedule
from test_storage import CSV, collector, db, started  # noqa: F401  (shared disposable fixture)
from test_monitor import Clock, SESSION_OPEN, campaign_files, offline_monitor, run_campaign  # noqa: F401


OPEN = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
AS_OF = OPEN + timedelta(hours=5, minutes=30)          # 19:00Z: s6 (19:30) is not yet due.
CONFIG = {"providers": {"valuation": "yahoo", "comparison": ["finnhub"]},
          "scheduler": {"poll_interval_seconds": 3600}}
MAINTENANCE = [{"start": "2026-09-08T16:00:00+00:00", "end": "2026-09-08T18:00:00+00:00"}]


def _quote_row(identity, attempt, *, price, quote_time, received, flags=(), delay=0):
    return {"id": identity, "attempt_id": attempt, "instrument_id": "us-aapl", "ticker": "AAPL",
            "provider_symbol": "AAPL", "market": "US", "currency": "USD", "provider": "yahoo",
            "price": price, "price_kind": "last_trade", "quote_time": quote_time, "received_at": received,
            "trading_date": date(2026, 9, 8), "session": "regular", "time_precision": "second",
            "declared_delay_seconds": delay, "quality_flags": list(flags), "asset_type": "stock",
            "source_timezone": "America/New_York", "source_time_raw": None}


def _attempt(identity, cycle, *, provider, ticker, number, status, elapsed, executed):
    return {"id": identity, "run_id": None, "cycle_id": cycle, "provider": provider,
            "instrument_id": "us-aapl" if ticker == "AAPL" else f"unresolved:US:{ticker}",
            "ticker": ticker, "attempt_number": number, "started_at": OPEN, "completed_at": OPEN,
            "recovered_at": None, "status": status, "elapsed_ms": elapsed,
            "error_code": None if status == "success" else status, "response_hash": "hash",
            "response_evidence": {"status": status, "adapter": {"executed": executed}}}


def observation():
    """One interrupted run inside a seven-opportunity plan; every count is checkable by hand.

    Plan (US, 3600s interval): 13:30 regular fresh, 14:30 regular stale, 15:30 regular skipped,
    16:30 and 17:30 regular missing (downtime), 18:30 post_close unknown time, 19:30 not yet due.
    """
    run = uuid4()
    cycles = {"fresh": uuid4(), "stale": uuid4(), "skipped": uuid4(), "unknown": uuid4()}
    holdings = {"AAPL": uuid4(), "ZZZZ": uuid4()}
    quote_ids = {name: uuid4() for name in ("fresh", "stale", "unknown", "finnhub")}
    attempt_ids = {name: uuid4() for name in
                   ("fresh", "fresh_zzzz", "finnhub", "stale_timeout", "stale_retry", "stale_zzzz",
                    "stale_finnhub", "unknown", "unknown_zzzz")}
    scheduled = [
        ("s0", "regular", OPEN, cycles["fresh"], "completed"),
        ("s1", "regular", OPEN + timedelta(hours=1), cycles["stale"], "completed"),
        ("s2", "regular", OPEN + timedelta(hours=2), cycles["skipped"], "skipped"),
        ("s3", "regular", OPEN + timedelta(hours=3), None, None),
        ("s4", "regular", OPEN + timedelta(hours=4), None, None),
        ("s5", "post_close", OPEN + timedelta(hours=5), cycles["unknown"], "completed"),
        ("s6", "regular", OPEN + timedelta(hours=6), None, None),
    ]
    campaign_id = uuid4()
    schedule = [{"id": uuid4(), "campaign_id": campaign_id, "market": "US", "scheduled_at": stamp,
                 "window_type": window, "cycle_id": cycle, "run_id": None if cycle is None else run,
                 "cycle_status": status, "due": stamp <= AS_OF}
                for _, window, stamp, cycle, status in scheduled]
    campaign = {
        "id": campaign_id, "planned_start": OPEN, "planned_end": OPEN + timedelta(days=1),
        "ended_at": None, "status": "running", "input_snapshot": "ticker,buy_price,quantity\n",
        "input_hash": "input-hash", "config_snapshot": CONFIG, "config_hash": "config-hash",
        "source_instruments": [{"provider": "yahoo", "instrument_id": "us-aapl", "ticker": "AAPL", "market": "US"}],
        "calendar_version": "exchange-calendars/test", "schedule_version": "monitor-v1",
        "threshold_version": "unconfirmed-v1", "maintenance_windows": MAINTENANCE,
    }
    cycle_rows = [
        {"id": cycles["fresh"], "run_id": run, "campaign_id": campaign_id, "scheduled_cycle_id": schedule[0]["id"],
         "market": "US", "scheduled_at": OPEN, "started_at": OPEN, "completed_at": OPEN,
         "recovered_at": None, "status": "completed", "reason": None},
        {"id": cycles["stale"], "run_id": run, "campaign_id": campaign_id, "scheduled_cycle_id": schedule[1]["id"],
         "market": "US", "scheduled_at": OPEN + timedelta(hours=1), "started_at": OPEN + timedelta(hours=1),
         "completed_at": OPEN + timedelta(hours=1), "recovered_at": None, "status": "completed", "reason": None},
        {"id": cycles["skipped"], "run_id": run, "campaign_id": campaign_id, "scheduled_cycle_id": schedule[2]["id"],
         "market": "US", "scheduled_at": OPEN + timedelta(hours=2), "started_at": OPEN + timedelta(hours=2),
         "completed_at": OPEN + timedelta(hours=2), "recovered_at": None, "status": "skipped",
         "reason": "scheduler_lag"},
        {"id": cycles["unknown"], "run_id": run, "campaign_id": campaign_id, "scheduled_cycle_id": schedule[5]["id"],
         "market": "US", "scheduled_at": OPEN + timedelta(hours=5), "started_at": OPEN + timedelta(hours=5),
         "completed_at": OPEN + timedelta(hours=5), "recovered_at": None, "status": "completed", "reason": None},
    ]
    attempts = [
        _attempt(attempt_ids["fresh"], cycles["fresh"], provider="yahoo", ticker="AAPL", number=1,
                 status="success", elapsed=120, executed=True),
        _attempt(attempt_ids["fresh_zzzz"], cycles["fresh"], provider="yahoo", ticker="ZZZZ", number=1,
                 status="unsupported_symbol", elapsed=0, executed=False),
        _attempt(attempt_ids["finnhub"], cycles["fresh"], provider="finnhub", ticker="AAPL", number=1,
                 status="success", elapsed=300, executed=True),
        _attempt(attempt_ids["stale_timeout"], cycles["stale"], provider="yahoo", ticker="AAPL", number=1,
                 status="timeout", elapsed=10000, executed=True),
        _attempt(attempt_ids["stale_retry"], cycles["stale"], provider="yahoo", ticker="AAPL", number=2,
                 status="success", elapsed=200, executed=True),
        _attempt(attempt_ids["stale_zzzz"], cycles["stale"], provider="yahoo", ticker="ZZZZ", number=1,
                 status="unsupported_symbol", elapsed=0, executed=False),
        _attempt(attempt_ids["stale_finnhub"], cycles["stale"], provider="finnhub", ticker="AAPL", number=1,
                 status="rate_limited", elapsed=0, executed=False),
        _attempt(attempt_ids["unknown"], cycles["unknown"], provider="yahoo", ticker="AAPL", number=1,
                 status="success", elapsed=150, executed=True),
        _attempt(attempt_ids["unknown_zzzz"], cycles["unknown"], provider="yahoo", ticker="ZZZZ", number=1,
                 status="unsupported_symbol", elapsed=0, executed=False),
    ]
    for attempt in attempts:
        attempt["run_id"] = run
    comparison = _quote_row(quote_ids["finnhub"], attempt_ids["finnhub"], price=Decimal("200.10"),
                            quote_time=OPEN - timedelta(seconds=30), received=OPEN)
    comparison.update(provider="finnhub", provider_symbol="AAPL")
    quotes = [
        _quote_row(quote_ids["fresh"], attempt_ids["fresh"], price=Decimal("200.10"),
                   quote_time=OPEN - timedelta(seconds=30), received=OPEN),
        comparison,
        _quote_row(quote_ids["stale"], attempt_ids["stale_retry"], price=Decimal("199.00"),
                   quote_time=OPEN - timedelta(minutes=30), received=OPEN + timedelta(hours=1),
                   flags=("stale",)),
        _quote_row(quote_ids["unknown"], attempt_ids["unknown"], price=Decimal("198.00"),
                   quote_time=None, received=OPEN + timedelta(hours=5), flags=("time_unknown",), delay=None),
    ]
    quotes[-1]["time_precision"] = "unknown"
    valuations, totals = [], []
    for name, cycle, quote_id, value, flags in (
            ("fresh", cycles["fresh"], quote_ids["fresh"], Decimal("500.250"), []),
            ("stale", cycles["stale"], quote_ids["stale"], Decimal("497.500"), ["stale"]),
            ("unknown", cycles["unknown"], quote_ids["unknown"], Decimal("495.000"), ["time_unknown"])):
        valuations.append({"cycle_id": cycle, "holding_id": holdings["AAPL"], "run_id": run,
                           "quote_id": quote_id, "market_value": value, "quality_flags": flags,
                           "failure_reason": None})
        valuations.append({"cycle_id": cycle, "holding_id": holdings["ZZZZ"], "run_id": run,
                           "quote_id": None, "market_value": None, "quality_flags": [],
                           "failure_reason": "missing_quote"})
        totals.append({"cycle_id": cycle, "currency": "USD", "known_subtotal": value, "total": None,
                       "holding_count": 2, "valued_count": 1, "missing_count": 1,
                       "degraded_count": 1 if flags else 0,
                       "completeness": "partial"})
    snapshot = {
        "run": {"id": run, "campaign_id": campaign_id, "started_at": OPEN - timedelta(minutes=30),
                "ended_at": AS_OF, "heartbeat_at": AS_OF, "recovered_at": None, "status": "interrupted",
                "package_version": "0.1.0", "image_id": "sha256:test", "input_snapshot": CSV,
                "input_hash": "input-hash", "config_snapshot": CONFIG, "config_hash": "config-hash"},
        "holdings": [{"id": holdings["AAPL"], "run_id": run, "ticker": "AAPL", "market": "US",
                      "currency": "USD", "buy_price": Decimal("180"), "quantity": Decimal("2.5")},
                     {"id": holdings["ZZZZ"], "run_id": run, "ticker": "ZZZZ", "market": "US",
                      "currency": "USD", "buy_price": Decimal("10"), "quantity": Decimal("1")}],
        "cycles": cycle_rows, "fetch_attempts": attempts, "quotes": quotes,
        "valuations": valuations, "totals": totals,
    }
    return campaign, schedule, snapshot


@pytest.fixture
def report():
    campaign, schedule, snapshot = observation()
    return build_run(snapshot, as_of=AS_OF, schedule=run_schedule(schedule, snapshot["run"], as_of=AS_OF),
                     maintenance=campaign["maintenance_windows"], campaign=campaign)


def test_percentile_uses_nearest_rank_without_inventing_samples():
    assert percentile([], 0.95) is None
    assert percentile([5], 0.5) == 5
    assert [percentile([120, 150, 200, 300, 10000], fraction) for fraction in (0.5, 0.95)] == [200, 10000]


def test_source_metrics_keep_first_attempt_and_unexecuted_operations_honest(report):
    metrics, volume = report["metrics"], report["volume"]
    # 9 operations over 8 opportunities; only 5 reached a source, and one of those was a retry.
    assert (volume["fetch_opportunities"], volume["fetch_operations"],
            volume["executed_operations"], volume["retry_operations"]) == (8, 9, 5, 1)
    assert metrics["first_attempt_success"] == {"numerator": 3, "denominator": 4, "rate": 0.75}
    assert metrics["retry_success"]["numerator"] == 4 and metrics["retry_success"]["denominator"] == 4
    assert metrics["retry_success"]["meets_threshold"] is True
    # Cooldown and unsupported symbols never entered a source, so they stay out of both denominators.
    assert report["incidents"]["not_executed_operations"] == 4
    assert report["by_provider"]["finnhub"]["executed_opportunities"] == 1
    assert report["by_provider"]["finnhub"]["retry_success"]["denominator"] == 1
    assert report["by_ticker"]["ZZZZ"]["retry_success"]["rate"] is None
    assert report["metrics"]["operation_latency"]["p50_ms"] == 200
    assert report["metrics"]["operation_latency"]["p95_seconds"] == 10.0
    assert report["metrics"]["catalog_coverage"] == {"numerator": 1, "denominator": 2, "rate": 0.5}
    assert report["coverage"]["unsupported"][0]["ticker"] == "ZZZZ"


def test_schedule_coverage_keeps_downtime_and_cooldown_in_the_denominator(report):
    schedule = report["schedule"]
    # Six due opportunities: three completed, one skipped, two never recorded.
    assert schedule["including_maintenance"] == {
        "planned": 6, "executed": 3, "skipped": 1, "interrupted": 0, "running": 0, "missing": 2,
        "coverage": {"numerator": 3, "denominator": 6, "rate": 0.5, "threshold": 0.99,
                     "threshold_status": "proposed_unconfirmed", "meets_threshold": False}}
    assert schedule["excluding_maintenance"]["planned"] == 4
    assert schedule["excluding_maintenance"]["coverage"]["rate"] == 0.75
    assert schedule["by_window_type"]["post_close"]["planned"] == 1
    assert report["incidents"]["skip_reasons"] == {"scheduler_lag": 1}
    assert report["incidents"]["downtime_windows"] == [
        {"market": "US", "from": (OPEN + timedelta(hours=3)).isoformat(),
         "to": (OPEN + timedelta(hours=4)).isoformat(), "missing_count": 2, "duration_seconds": 7200.0}]


def test_freshness_denominator_comes_from_the_plan_and_late_samples_stay_undetermined(report):
    fresh = report["freshness"]
    # Five due regular windows x two holdings; post-close and not-yet-due windows are excluded.
    assert fresh["qualified_opportunities"] == 10
    assert fresh["outcome"] == {"fresh": 1, "late_or_stale": 1, "unknown_time": 0, "missing": 8}
    assert fresh["excluded"] == {"not_yet_due": 0, "opening_delay": 0, "post_close": 2}
    assert fresh["freshness_rate"]["rate"] == 0.1
    assert fresh["verdict"] == "insufficient_evidence"
    assert "無法獨立判斷" in fresh["verdict_reason"]
    late = [row for row in fresh["samples"] if row["outcome"] == "late_or_stale"]
    assert late[0]["quote_age_seconds"] == 5400.0
    assert report["incidents"]["unknown_time_quotes"] == 1
    assert report["incidents"]["cache_usage"] == {"cached": 0, "stale": 1}
    assert report["incidents"]["degraded_valuations"] == 2
    assert report["incidents"]["missing_valuations"] == 3


def test_price_comparison_only_counts_aligned_samples_with_a_known_tick(report):
    comparison = report["price_comparison"]
    assert (comparison["total_samples"], comparison["aligned_samples"]) == (1, 1)
    assert comparison["match_rate"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert comparison["samples"][0]["difference"] == "0.00" and comparison["samples"][0]["within_tick"] is True
    assert comparison["over_threshold"] == []
    assert comparison["undetermined_threshold_samples"] == 0


def _taiwan_document(asset_type):
    campaign, schedule, snapshot = observation()
    for row in snapshot["quotes"] + snapshot["cycles"] + snapshot["holdings"]:
        row["market"] = "TW"
    for row in snapshot["quotes"] + snapshot["holdings"]:
        row["currency"] = "TWD"
    for row in snapshot["quotes"]:
        row["asset_type"] = asset_type
    for row in schedule:
        row["market"] = "TW"
    return build_run(snapshot, as_of=AS_OF, schedule=run_schedule(schedule, snapshot["run"], as_of=AS_OF),
                     maintenance=campaign["maintenance_windows"], campaign=campaign)


@pytest.mark.parametrize("asset_type,tick", [("stock", "0.5"), ("etf", "0.05")])
def test_taiwan_tick_size_comes_from_the_official_table_for_the_stored_type(asset_type, tick):
    # Fixture prices are 198.00 and 198.00: a 100-500 stock ticks at 0.5, an ETF over 50 at 0.05.
    document = _taiwan_document(asset_type)
    comparison = document["price_comparison"]
    sample = comparison["samples"][0]
    assert comparison["aligned_samples"] == 1
    assert (sample["asset_type"], sample["tick_size"]) == (asset_type, tick)
    assert sample["within_tick"] is True and "undetermined_reason" not in sample
    assert comparison["match_rate"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert comparison["undetermined_threshold_samples"] == 0


def test_taiwan_tick_size_stays_undetermined_without_a_stored_asset_type():
    document = _taiwan_document(None)
    comparison = document["price_comparison"]
    assert comparison["aligned_samples"] == 1
    assert comparison["samples"][0]["within_tick"] is None
    assert comparison["samples"][0]["undetermined_reason"] == "tick_size_unknown"
    assert comparison["match_rate"] == {"numerator": 0, "denominator": 0, "rate": None}
    assert any("最小報價單位" in item for item in document["conclusions"]["open_cases"])


@pytest.mark.parametrize("asset_type,price,tick", [
    ("stock", "9.99", "0.01"), ("stock", "10", "0.05"), ("stock", "49.95", "0.05"),
    ("stock", "50", "0.1"), ("stock", "99.9", "0.1"), ("stock", "100", "0.5"),
    ("stock", "499.5", "0.5"), ("stock", "500", "1"), ("stock", "999", "1"),
    ("stock", "1000", "5"), ("stock", "1350", "5"),
    ("etf", "49.99", "0.01"), ("etf", "50", "0.05"), ("etf", "220.15", "0.05"),
])
def test_taiwan_tick_table_boundaries_follow_the_official_brackets(asset_type, price, tick):
    assert reporting.tick_size("TW", Decimal(price), asset_type) == Decimal(tick)


def test_tick_size_rejects_unusable_inputs_instead_of_guessing():
    assert reporting.tick_size("US", Decimal("198.00"), None) == Decimal("0.01")
    assert reporting.tick_size("TW", Decimal("198.00"), "warrant") is None
    assert reporting.tick_size("TW", None, "stock") is None
    assert reporting.tick_size("TW", Decimal("0"), "stock") is None


def test_valuation_recomputation_and_completeness_are_manually_checkable(report):
    check = report["valuation_check"]
    assert check["completeness_counts"] == {"partial": 3}
    assert check["recomputation_agrees"] is True and check["mismatches"] == []
    entry = check["manual_check_cycles"][0]           # Latest completed cycle for the market.
    assert entry["market"] == "US"
    aapl = next(row for row in entry["holdings"] if row["ticker"] == "AAPL")
    assert (aapl["quantity"], aapl["price"]) == ("2.5", "198.00")
    assert aapl["stored_market_value"] == aapl["recomputed_market_value"] == "495.000"
    assert aapl["display"] == "495.00"
    missing = next(row for row in entry["holdings"] if row["ticker"] == "ZZZZ")
    assert missing["stored_market_value"] is None and missing["failure_reason"] == "missing_quote"
    subtotal = entry["subtotals"][0]
    assert subtotal["stored_known_subtotal"] == subtotal["recomputed_known_subtotal"] == "495.000"
    assert subtotal["total"] is None and subtotal["completeness"] == "partial"
    assert subtotal["display_tail_difference"] == "0.00"


def test_conclusions_never_claim_more_than_the_record_supports(report):
    result = {row["case"]: row for row in report["conclusions"]["classification"]}
    assert result["V04 Decimal 估值與持久化往返"]["result"] == "符合"
    assert result["V09 儲存、恢復與失敗可見性"]["result"] == "部分符合"
    # One trading day and no confirmed thresholds cannot prove continuous observation.
    assert result["V10 持續觀測與價格交叉比對"]["result"] == "證據不足"
    assert report["identity"]["trading_days"] == {"US": ["2026-09-08"]}
    assert any("V01" in item for item in report["conclusions"]["open_cases"])
    assert any("尚未確認" in item for item in report["conclusions"]["limitations"])
    markdown = reporting.render_markdown(
        {"report_version": reporting.REPORT_VERSION, "scope": "run", "identity": report["identity"]["run_id"],
         "generated_at": AS_OF.isoformat(), "as_of": AS_OF.isoformat(), "thresholds": reporting.THRESHOLDS,
         "report_host": {"python": "3.14.7", "platform": "test"}, "report": report})
    for heading in ("## 1. 觀測範圍與版本", "## 4. 失敗、缺漏、快取與停機", "## 5. 價格比對",
                    "## 6. 小計人工核對與完整性", "## 7. 結論、限制與未完成項目"):
        assert heading in markdown
    assert "證據不足" in markdown and "建議門檻 99%：未達" in markdown


def test_campaign_report_aggregates_runs_against_one_immutable_plan():
    campaign, schedule, snapshot = observation()
    document = build_campaign({"campaign": campaign, "scheduled_cycles": schedule, "runs": [snapshot]},
                              as_of=AS_OF)
    assert document["identity"]["campaign_id"] == str(campaign["id"])
    assert document["volume"]["run_count"] == 1 and document["volume"]["scheduled_total"] == 7
    # The campaign sees the whole plan, including the opportunity that is not yet due.
    assert document["schedule"]["not_yet_due"] == 1 and document["schedule"]["due"] == 6
    assert document["metrics"]["schedule_coverage"]["rate"] == 0.5
    assert document["metrics"]["schedule_coverage_excluding_maintenance"]["rate"] == 0.75
    assert document["freshness"]["excluded"]["not_yet_due"] == 2
    assert [row["identity"]["run_id"] for row in document["runs"]] == [str(snapshot["run"]["id"])]
    assert json.dumps(document, ensure_ascii=False)          # No Decimal or datetime leaks into JSON.
    assert any("未到期" in item for item in document["conclusions"]["open_cases"])


def test_run_without_campaign_reports_no_schedule_denominator():
    _, _, snapshot = observation()
    snapshot["run"]["campaign_id"] = None
    document = build_run(snapshot, as_of=AS_OF)
    assert document["schedule"] is None and document["freshness"] is None
    assert document["metrics"]["schedule_coverage"] is None
    assert document["metrics"]["freshness_rate"] is None
    assert document["metrics"]["first_attempt_success"]["rate"] == 0.75
    assert any("沒有預定輪次" in item for item in document["conclusions"]["open_cases"])
    assert "排程覆蓋率與時效達標率無法計算" in reporting.render_markdown(
        {"report_version": reporting.REPORT_VERSION, "scope": "run", "identity": "x",
         "generated_at": AS_OF.isoformat(), "as_of": AS_OF.isoformat(), "thresholds": reporting.THRESHOLDS,
         "report_host": {"python": "3.14.7", "platform": "test"}, "report": document})


def test_execute_requires_exactly_one_scope(tmp_path):
    for kwargs in ({}, {"run_id": str(uuid4()), "campaign_id": str(uuid4())}):
        with pytest.raises(ConfigurationError, match="其中之一"):
            reporting.execute(tmp_path / "config.toml", tmp_path / "output", **kwargs)
    with pytest.raises(ConfigurationError, match="UUID"):
        reporting.execute(tmp_path / "config.toml", tmp_path / "output", run_id="not-a-uuid")
    assert not (tmp_path / "output").exists()


def test_report_reads_a_live_campaign_without_taking_the_collection_lock(db, monkeypatch, tmp_path):
    cfg, _ = db
    with collector(cfg):
        pass
    fetch = offline_monitor(monkeypatch, cfg)
    source, config = campaign_files(tmp_path)
    stop = Event()
    clock = Clock(SESSION_OPEN, stop=stop, stop_after=1)
    _, _, monitored = run_campaign(source, config, tmp_path / "output", clock=clock, stop=stop, fetch=fetch)
    assert [row["status"] for row in monitored["cycles"]] == ["completed"]

    monkeypatch.setattr(reporting, "load_database_config", lambda _: cfg)
    as_of = SESSION_OPEN + timedelta(hours=1)
    with Storage(cfg) as holder:
        holder.acquire_lock()                  # A live collector keeps the lock; report must not need it.
        code, directory, document = reporting.execute(config, tmp_path / "output",
                                                      run_id=monitored["run_id"], as_of=as_of)
    assert code == 0 and document["scope"] == "run"
    assert json.loads((directory / "report.json").read_text(encoding="utf-8")) == json.loads(
        json.dumps(document, ensure_ascii=False))
    assert "# 可靠性報告" in (directory / "report.md").read_text(encoding="utf-8")
    body = document["report"]
    assert body["identity"]["campaign_id"] == monitored["campaign_id"]
    assert body["identity"]["image_id"] and body["identity"]["package_version"]
    assert body["volume"]["cycles_completed"] == 1
    assert body["metrics"]["catalog_coverage"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert body["metrics"]["first_attempt_success"]["rate"] == 1.0
    # The run's own share of the plan ends when the run ended; later gaps belong to the campaign.
    assert body["schedule"]["including_maintenance"]["executed"] == 1
    assert body["valuation_check"]["recomputation_agrees"] is True

    campaign = reporting.execute(config, tmp_path / "output",
                                 campaign_id=monitored["campaign_id"], as_of=as_of)[2]["report"]
    assert campaign["volume"]["run_count"] == 1
    assert campaign["identity"]["runs"][0]["run_id"] == monitored["run_id"]
    # The stopped process left the 14:30 opportunity unclaimed; it stays in the denominator.
    plan = campaign["schedule"]["including_maintenance"]
    assert plan["planned"] == plan["executed"] + plan["missing"] and plan["missing"] >= 1
    assert campaign["incidents"]["downtime_windows"]
    assert campaign["freshness"]["outcome"]["missing"] >= 1
    with pytest.raises(ConfigurationError, match="不存在"):
        reporting.execute(config, tmp_path / "output", run_id=str(uuid4()))


def test_schedule_query_requires_a_snapshot_and_an_existing_campaign(db):
    cfg, _ = db
    with collector(cfg) as storage:
        run, cycle = started(storage)
        storage.finish_cycle(cycle, selected_quotes={})
        storage.finish_run(run)
    with Storage(cfg) as reader:
        with pytest.raises(StorageError, match="report_snapshot"):
            reader.read_schedule(uuid4(), as_of=datetime.now(UTC))
        with reader.report_snapshot():
            with pytest.raises(ValueError):
                reader.read_schedule(uuid4(), as_of=datetime.now(UTC))
            # A single quote run keeps no campaign, so its report has no plan to compare against.
            assert reader.read_run(run)["run"]["campaign_id"] is None

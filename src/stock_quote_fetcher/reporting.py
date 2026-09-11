"""Read-only reliability reporting. Denominators come from the plan, not from what ran."""

from datetime import UTC, datetime
from decimal import Decimal
import json
import math
from pathlib import Path
import platform
import sys
from uuid import UUID

from stock_quote_fetcher.config import ConfigurationError, load_database_config
from stock_quote_fetcher.models import Market, Quote
from stock_quote_fetcher.quality import timezone
from stock_quote_fetcher.storage import Storage


REPORT_VERSION = "step8-v1"

# Proposed in the acceptance plan and still unconfirmed; every output labels them as such.
THRESHOLDS = {
    "version": "unconfirmed-v1",
    "status": "proposed_unconfirmed",
    "declared_delay_seconds": 1200,
    "quote_age_seconds": 1270,
    "retry_success_rate": 0.99,
    "schedule_coverage_rate": 0.99,
    "freshness_rate": 0.95,
    "operation_p95_seconds": 10,
    "minimum_trading_days": 3,
}

UNKNOWN_TIME_FLAGS = frozenset({"time_unknown", "freshness_unknown", "future_time"})
CACHE_FLAGS = ("cached", "stale")


def _stamp(value):
    return value.isoformat() if value is not None else None


def _decimal(value):
    return format(value, "f") if value is not None else None


def _flags(row, key="quality_flags"):
    return frozenset(row.get(key) or ())


def _quote(row):
    return Quote(**{key: row[key] for key in Quote.__dataclass_fields__})


def counts(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def ratio(numerator, denominator, *, threshold=None):
    """A zero denominator stays visible as null; it is never reported as 100%."""
    result = {"numerator": numerator, "denominator": denominator,
              "rate": None if not denominator else numerator / denominator}
    if threshold is not None:
        result["threshold"] = threshold
        result["threshold_status"] = THRESHOLDS["status"]
        result["meets_threshold"] = None if result["rate"] is None else result["rate"] >= threshold
    return result


def percentile(values, fraction):
    """Nearest-rank: interpolation would invent a sample this observation never produced."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def latency(samples):
    p95 = percentile(samples, 0.95)
    return {"samples": len(samples), "p50_ms": percentile(samples, 0.5), "p95_ms": p95,
            "max_ms": max(samples) if samples else None,
            "p95_seconds": None if p95 is None else p95 / 1000,
            "threshold_seconds": THRESHOLDS["operation_p95_seconds"],
            "threshold_status": THRESHOLDS["status"],
            "meets_threshold": None if p95 is None else p95 / 1000 <= THRESHOLDS["operation_p95_seconds"]}


def executed(attempt):
    """Only adapter-recorded execution counts; cooldown or budget skips never reached a source."""
    evidence = attempt.get("response_evidence") or {}
    adapter = evidence.get("adapter") if isinstance(evidence, dict) else None
    return bool(adapter.get("executed")) if isinstance(adapter, dict) else False


def opportunities(attempts, markets):
    """One fetch opportunity is one (cycle, provider, instrument); its retries stay inside it."""
    groups = {}
    for attempt in sorted(attempts, key=lambda row: (str(row["cycle_id"]), row["provider"],
                                                     row["instrument_id"], row["attempt_number"])):
        key = (attempt["cycle_id"], attempt["provider"], attempt["instrument_id"])
        group = groups.get(key)
        if group is None:
            group = groups[key] = {"cycle_id": attempt["cycle_id"], "provider": attempt["provider"],
                                   "ticker": attempt["ticker"], "market": markets.get(attempt["cycle_id"]),
                                   "attempts": []}
        group["attempts"].append(attempt)
    for group in groups.values():
        rows = group["attempts"]
        first = next((row for row in rows if row["attempt_number"] == 1), None)
        group.update(first_executed=bool(first and executed(first)),
                     first_success=bool(first and executed(first) and first["status"] == "success"),
                     executed_any=any(executed(row) for row in rows),
                     success=any(row["status"] == "success" for row in rows),
                     retries=sum(1 for row in rows if row["attempt_number"] > 1),
                     elapsed=[row["elapsed_ms"] for row in rows if executed(row) and row["elapsed_ms"] is not None],
                     statuses=[row["status"] for row in rows])
    return list(groups.values())


def aggregate(groups):
    ran = [group for group in groups if group["executed_any"]]
    return {
        "opportunities": len(groups),
        "executed_opportunities": len(ran),
        "operations": sum(len(group["attempts"]) for group in groups),
        "executed_operations": sum(sum(executed(row) for row in group["attempts"]) for group in groups),
        "retry_operations": sum(group["retries"] for group in groups),
        "first_attempt_success": ratio(sum(group["first_success"] for group in groups),
                                       sum(group["first_executed"] for group in groups)),
        "retry_success": ratio(sum(group["success"] for group in ran), len(ran),
                               threshold=THRESHOLDS["retry_success_rate"]),
        "latency": latency([value for group in groups for value in group["elapsed"]]),
        "status_counts": counts([status for group in groups for status in group["statuses"]]),
    }


def grouped(groups, key):
    buckets = {}
    for group in groups:
        buckets.setdefault(str(key(group)), []).append(group)
    return {name: aggregate(rows) for name, rows in sorted(buckets.items())}


def coverage(holdings, attempts, quotes, *, valuation):
    """Verifiable means the catalog mapping yielded a quote with matching currency and valid price."""
    priced = {}
    for row in quotes:
        if row["provider"] == valuation:
            priced.setdefault(row["ticker"], []).append(row)
    reasons = {}
    for attempt in attempts:
        if attempt["provider"] == valuation and attempt["status"] != "success":
            reasons.setdefault(attempt["ticker"], set()).add(attempt["status"])
    verified, unsupported, unverified = [], [], []
    for holding in sorted(holdings, key=lambda row: (row["market"], row["ticker"])):
        entry = {"ticker": holding["ticker"], "market": holding["market"], "currency": holding["currency"]}
        usable = [row for row in priced.get(holding["ticker"], ())
                  if row["currency"] == holding["currency"] and row["market"] == holding["market"]
                  and row["price"].is_finite() and row["price"] > 0]
        if usable:
            verified.append(entry)
        elif "unsupported_symbol" in reasons.get(holding["ticker"], ()):
            unsupported.append({**entry, "reason": "unsupported_symbol"})
        else:
            unverified.append({**entry, "reason": ",".join(sorted(reasons.get(holding["ticker"]) or {"no_attempt"}))})
    return {"catalog_coverage": ratio(len(verified), len(holdings)),
            "verified": verified, "unsupported": unsupported, "unverified": unverified}


def due(row, as_of):
    """A claimed opportunity is due whatever the clock says; skew must not shrink a denominator."""
    return row["scheduled_at"] <= as_of or row["cycle_id"] is not None


def in_maintenance(stamp, windows):
    for window in windows or ():
        try:
            start = datetime.fromisoformat(window["start"])
            end = datetime.fromisoformat(window["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if start <= stamp < end:
            return True
    return False


def schedule_coverage(schedule, *, as_of, maintenance):
    """Downtime and cooldown skips stay in the denominator; only completed cycles count as executed."""
    def summarize(rows):
        status = counts([row["cycle_status"] or "missing" for row in rows])
        return {"planned": len(rows), "executed": status.get("completed", 0),
                "skipped": status.get("skipped", 0), "interrupted": status.get("interrupted", 0),
                "running": status.get("running", 0), "missing": status.get("missing", 0),
                "coverage": ratio(status.get("completed", 0), len(rows),
                                  threshold=THRESHOLDS["schedule_coverage_rate"])}

    arrived = [row for row in schedule if due(row, as_of)]
    planned = [row for row in arrived if not in_maintenance(row["scheduled_at"], maintenance)]
    return {"scheduled_total": len(schedule), "due": len(arrived), "not_yet_due": len(schedule) - len(arrived),
            "maintenance_windows": list(maintenance or ()),
            "including_maintenance": summarize(arrived),
            "excluding_maintenance": summarize(planned),
            "by_market": {market: summarize([row for row in arrived if row["market"] == market])
                          for market in sorted({row["market"] for row in arrived})},
            "by_window_type": {kind: summarize([row for row in arrived if row["window_type"] == kind])
                               for kind in sorted({row["window_type"] for row in arrived})}}


def downtime(schedule, *, as_of, poll_seconds):
    """Rebuild the gaps a stopped process left, from the plan rather than from records."""
    missing = sorted((row for row in schedule if due(row, as_of) and row["cycle_id"] is None),
                     key=lambda row: (row["market"], row["scheduled_at"]))
    windows = []
    for row in missing:
        current = windows[-1] if windows else None
        if (current and current["market"] == row["market"]
                and (row["scheduled_at"] - current["last"]).total_seconds() <= poll_seconds):
            current.update(last=row["scheduled_at"], missing_count=current["missing_count"] + 1)
        else:
            windows.append({"market": row["market"], "first": row["scheduled_at"],
                            "last": row["scheduled_at"], "missing_count": 1})
    return [{"market": window["market"], "from": _stamp(window["first"]), "to": _stamp(window["last"]),
             "missing_count": window["missing_count"],
             "duration_seconds": (window["last"] - window["first"]).total_seconds() + poll_seconds}
            for window in windows]


def freshness(schedule, *, as_of, holdings, cycle_quotes, valuation):
    """Only regular windows qualify: opening delay and post-close observation are excluded by design."""
    tickers = {}
    for holding in holdings:
        tickers.setdefault(holding["market"], []).append(holding["ticker"])
    outcome = {"fresh": 0, "late_or_stale": 0, "unknown_time": 0, "missing": 0}
    excluded = {"not_yet_due": 0, "opening_delay": 0, "post_close": 0}
    samples = []
    for row in schedule:
        population = len(tickers.get(row["market"], ()))
        if not due(row, as_of):
            excluded["not_yet_due"] += population
            continue
        if row["window_type"] != "regular":
            excluded[row["window_type"]] = excluded.get(row["window_type"], 0) + population
            continue
        for ticker in sorted(tickers.get(row["market"], ())):
            quote = cycle_quotes.get((row["cycle_id"], ticker, valuation)) if row["cycle_id"] else None
            if quote is None:
                outcome["missing"] += 1
                continue
            if quote["quote_time"] is None or _flags(quote) & UNKNOWN_TIME_FLAGS:
                outcome["unknown_time"] += 1
                samples.append({"ticker": ticker, "market": row["market"],
                                "scheduled_at": _stamp(row["scheduled_at"]), "outcome": "unknown_time",
                                "quote_time": _stamp(quote["quote_time"]),
                                "declared_delay_seconds": quote["declared_delay_seconds"],
                                "quality_flags": sorted(_flags(quote))})
                continue
            age = (quote["received_at"] - quote["quote_time"]).total_seconds()
            delay = quote["declared_delay_seconds"]
            if delay is None or delay > THRESHOLDS["declared_delay_seconds"] or age > THRESHOLDS["quote_age_seconds"]:
                outcome["late_or_stale"] += 1
                samples.append({"ticker": ticker, "market": row["market"],
                                "scheduled_at": _stamp(row["scheduled_at"]), "outcome": "late_or_stale",
                                "quote_age_seconds": age, "declared_delay_seconds": delay,
                                "quality_flags": sorted(_flags(quote))})
            else:
                outcome["fresh"] += 1
    qualified = sum(outcome.values())
    rate = ratio(outcome["fresh"], qualified, threshold=THRESHOLDS["freshness_rate"])
    if not qualified:
        verdict, reason = "insufficient_evidence", "沒有合格的一般交易時段觀測窗。"
    elif outcome["late_or_stale"]:
        # Whether a quote is old because nothing traded cannot be decided from stored data.
        verdict, reason = "insufficient_evidence", "有超過門檻的樣本，且無法獨立判斷是否因無成交而變舊。"
    elif rate["meets_threshold"]:
        verdict, reason = "meets_proposed_threshold", "全部合格機會符合建議時效規則；門檻本身尚未確認。"
    else:
        verdict, reason = "below_proposed_threshold", "合格機會未達建議時效率。"
    return {"rule": {"declared_delay_seconds": THRESHOLDS["declared_delay_seconds"],
                     "quote_age_seconds": THRESHOLDS["quote_age_seconds"],
                     "qualified_window_types": ["regular"],
                     "exclusion_rule": "排除休市、開盤延遲窗口與收盤後延長觀測；不因提高達標率而臨時排除樣本。"},
            "qualified_opportunities": qualified, "outcome": outcome, "excluded": excluded,
            "freshness_rate": rate, "verdict": verdict, "verdict_reason": reason,
            "samples": samples[:200], "sample_truncated": len(samples) > 200}


# Official Taiwan tick tables (TWSE 集中市場交易制度；TPEx 準用相同級距)。Lower bound is
# inclusive, so a price is matched against the first row whose upper bound it stays below.
TW_STOCK_TICKS = ((Decimal("10"), Decimal("0.01")), (Decimal("50"), Decimal("0.05")),
                  (Decimal("100"), Decimal("0.1")), (Decimal("500"), Decimal("0.5")),
                  (Decimal("1000"), Decimal("1")), (None, Decimal("5")))
TW_ETF_TICKS = ((Decimal("50"), Decimal("0.01")), (None, Decimal("0.05")))


def tick_size(market, price, asset_type=None):
    """US equities quote in cents. The TW table depends on the official security type, which
    quotes written before schema 0003 do not carry; those stay undetermined."""
    if market == "US":
        return Decimal("0.01")
    if asset_type not in ("stock", "etf") or price is None:
        return None
    table = TW_STOCK_TICKS if asset_type == "stock" else TW_ETF_TICKS
    value = Decimal(price)
    if not value.is_finite() or value <= 0:
        return None
    for upper, tick in table:
        if upper is None or value < upper:
            return tick
    return None


def price_comparison(cycle_quotes, *, valuation, comparison):
    """Compare persisted quotes only; the report never refetches to fill a comparison gap."""
    from stock_quote_fetcher.quoting import compare
    samples, unaligned_reasons = [], []
    comparable, matched = 0, 0
    for key, row in sorted(cycle_quotes.items(), key=lambda item: (str(item[0][0]), item[0][1], item[0][2])):
        cycle_id, ticker, provider = key
        if provider == valuation or (comparison and provider not in comparison):
            continue
        main = cycle_quotes.get((cycle_id, ticker, valuation))
        result = compare(_quote(main) if main else None, _quote(row), ticker, provider)
        tick = tick_size(row["market"], row["price"], row.get("asset_type"))
        sample = {"cycle_id": str(cycle_id), **result, "market": row["market"],
                  "asset_type": row.get("asset_type"), "tick_size": _decimal(tick)}
        if result["aligned"] and tick is not None:
            comparable += 1
            sample["within_tick"] = abs(Decimal(result["difference"])) <= tick
            matched += bool(sample["within_tick"])
        elif result["aligned"]:
            sample["within_tick"] = None
            sample["undetermined_reason"] = "tick_size_unknown"
        else:
            unaligned_reasons.append(result["reason"])
        samples.append(sample)
    aligned = [row for row in samples if row["aligned"]]
    return {"total_samples": len(samples), "aligned_samples": len(aligned),
            "undetermined_threshold_samples": sum(1 for row in aligned if row.get("within_tick") is None),
            "unaligned_reasons": counts(unaligned_reasons),
            "match_rate": ratio(matched, comparable),
            "over_threshold": [row for row in aligned if row.get("within_tick") is False][:50],
            "samples": samples[:200], "sample_truncated": len(samples) > 200,
            "note": "只有時間與價格口徑對齊、且能判定最小報價單位的樣本進入吻合率分母；比較來源共用上游時不構成獨立正確性證明。"}


def valuation_check(holdings, cycles, valuations, totals, quotes):
    """Recompute quantity x price and each subtotal from persisted rows for manual checking."""
    from stock_quote_fetcher.valuation import display_amount, exact_product, exact_sum
    by_holding = {row["id"]: row for row in holdings}
    by_quote = {row["id"]: row for row in quotes}
    per_cycle, per_cycle_totals = {}, {}
    for row in valuations:
        per_cycle.setdefault(row["cycle_id"], []).append(row)
    for row in totals:
        per_cycle_totals.setdefault(row["cycle_id"], []).append(row)
    latest = {}
    for cycle in sorted((row for row in cycles if row["status"] == "completed"),
                        key=lambda row: (row["scheduled_at"], str(row["id"]))):
        latest[cycle["market"]] = cycle
    checks, mismatches = [], []
    for market, cycle in sorted(latest.items()):
        rows = []
        for valuation in sorted(per_cycle.get(cycle["id"], ()),
                                key=lambda row: by_holding[row["holding_id"]]["ticker"]):
            holding = by_holding[valuation["holding_id"]]
            quote = by_quote.get(valuation["quote_id"])
            recomputed = exact_product(holding["quantity"], quote["price"]) if quote else None
            agrees = recomputed == valuation["market_value"]
            rows.append({"ticker": holding["ticker"], "currency": holding["currency"],
                         "quantity": _decimal(holding["quantity"]),
                         "price": _decimal(quote["price"]) if quote else None,
                         "provider": quote["provider"] if quote else None,
                         "stored_market_value": _decimal(valuation["market_value"]),
                         "recomputed_market_value": _decimal(recomputed),
                         "display": display_amount(valuation["market_value"]) if valuation["market_value"] is not None else None,
                         "quality_flags": sorted(_flags(valuation)),
                         "failure_reason": valuation["failure_reason"],
                         "recomputation_agrees": agrees})
            if not agrees:
                mismatches.append({"cycle_id": str(cycle["id"]), "ticker": holding["ticker"]})
        subtotals = []
        for total in sorted(per_cycle_totals.get(cycle["id"], ()), key=lambda row: row["currency"]):
            values = [row["market_value"] for row in per_cycle.get(cycle["id"], ())
                      if row["market_value"] is not None
                      and by_holding[row["holding_id"]]["currency"] == total["currency"]]
            recomputed = exact_sum(values)
            displayed = exact_sum([Decimal(display_amount(value)) for value in values]) if values else Decimal(0)
            agrees = recomputed == total["known_subtotal"]
            subtotals.append({"currency": total["currency"], "completeness": total["completeness"],
                              "holding_count": total["holding_count"], "valued_count": total["valued_count"],
                              "missing_count": total["missing_count"], "degraded_count": total["degraded_count"],
                              "stored_known_subtotal": _decimal(total["known_subtotal"]),
                              "recomputed_known_subtotal": _decimal(recomputed),
                              "known_subtotal_display": display_amount(total["known_subtotal"]),
                              "total": _decimal(total["total"]),
                              "sum_of_displayed_rows": _decimal(displayed),
                              "display_tail_difference": _decimal(
                                  displayed - Decimal(display_amount(total["known_subtotal"]))),
                              "recomputation_agrees": agrees})
            if not agrees:
                mismatches.append({"cycle_id": str(cycle["id"]), "currency": total["currency"]})
        checks.append({"market": market, "cycle_id": str(cycle["id"]),
                       "scheduled_at": _stamp(cycle["scheduled_at"]), "holdings": rows, "subtotals": subtotals})
    return {"manual_check_cycles": checks,
            "completeness_counts": counts([row["completeness"] for row in totals]),
            "mismatches": mismatches,
            "recomputation_agrees": not mismatches and bool(checks),
            "note": "顯示值以 ROUND_HALF_UP 至小數二位；列顯示值加總與小計顯示值的尾差為預期行為，精確值供人工核對。"}


def incidents(attempts, cycles, valuations, quotes, runs, schedule, *, as_of, poll_seconds):
    unknown_time = [row for row in quotes if row["quote_time"] is None or _flags(row) & UNKNOWN_TIME_FLAGS]
    return {
        "attempt_status_counts": counts([row["status"] for row in attempts]),
        "attempt_error_codes": counts([row["error_code"] for row in attempts if row["error_code"]]),
        "rate_limited_operations": sum(1 for row in attempts if row["status"] == "rate_limited"),
        "timeouts": sum(1 for row in attempts if row["status"] == "timeout"),
        "not_executed_operations": sum(1 for row in attempts if not executed(row)),
        "missing_valuations": sum(1 for row in valuations if row["market_value"] is None),
        "missing_reasons": counts([row["failure_reason"] for row in valuations if row["failure_reason"]]),
        "unknown_time_quotes": len(unknown_time),
        "cache_usage": {flag: sum(1 for row in valuations if flag in _flags(row)) for flag in CACHE_FLAGS},
        "degraded_valuations": sum(1 for row in valuations
                                   if row["market_value"] is not None and _flags(row) - {"market_closed"}),
        "cycle_status_counts": counts([row["status"] for row in cycles]),
        "skip_reasons": counts([row["reason"] for row in cycles if row["reason"]]),
        "downtime_windows": downtime(schedule, as_of=as_of, poll_seconds=poll_seconds),
        "recovery": {
            "runs_recovered": [{"run_id": str(row["id"]), "status": row["status"],
                                "recovered_at": _stamp(row["recovered_at"])}
                               for row in runs if row["recovered_at"]],
            "cycles_recovered": sum(1 for row in cycles if row["recovered_at"]),
            "attempts_recovered": sum(1 for row in attempts if row["recovered_at"]),
            "interrupted_runs": sum(1 for row in runs if row["status"] == "interrupted"),
        },
    }


def trading_days(cycles):
    result = {}
    for cycle in cycles:
        if cycle["status"] != "completed":
            continue
        local = cycle["scheduled_at"].astimezone(timezone(Market(cycle["market"])))
        result.setdefault(cycle["market"], set()).add(local.date().isoformat())
    return {market: sorted(days) for market, days in sorted(result.items())}


def cycle_quote_index(attempts, quotes):
    """Key persisted quotes by the cycle that fetched them; reused cache keeps its own cycle."""
    cycle_of = {row["id"]: row["cycle_id"] for row in attempts}
    index = {}
    for row in quotes:
        cycle_id = cycle_of.get(row["attempt_id"])
        if cycle_id is not None:
            index[(cycle_id, row["ticker"], row["provider"])] = row
    return index


def conclusions(*, scope, identity, coverage_section, schedule_section, freshness_section,
                comparison_section, valuation_section, incident_section, days, providers):
    """Only judge what the persisted observation supports; anything else stays insufficient."""
    classification, open_cases = [], []
    if valuation_section["manual_check_cycles"]:
        classification.append({
            "case": "V04 Decimal 估值與持久化往返",
            "result": "符合" if valuation_section["recomputation_agrees"] else "不符合",
            "reason": "以持久化的股數與價格重算每筆市值與小計，"
                      + ("全部一致。" if valuation_section["recomputation_agrees"] else "存在不一致，見 mismatches。")})
    else:
        classification.append({"case": "V04 Decimal 估值與持久化往返", "result": "證據不足",
                               "reason": "本範圍沒有已完成輪次的估值紀錄可重算。"})
    recovery = incident_section["recovery"]
    if recovery["runs_recovered"] or recovery["interrupted_runs"]:
        classification.append({"case": "V09 儲存、恢復與失敗可見性", "result": "部分符合",
                               "reason": "本範圍可見 interrupted 與 recovered_at 紀錄，失敗未被記成成功；"
                                         "互斥與資料庫故障案例由步驟 3／7 執行。"})
    else:
        classification.append({"case": "V09 儲存、恢復與失敗可見性", "result": "證據不足",
                               "reason": "本範圍沒有中斷或恢復紀錄可佐證恢復行為。"})
    observed = {market: len(value) for market, value in days.items()}
    enough_days = bool(days) and all(count >= THRESHOLDS["minimum_trading_days"] for count in observed.values())
    if comparison_section["match_rate"]["denominator"] and enough_days:
        classification.append({"case": "V10 持續觀測與價格交叉比對", "result": "部分符合",
                               "reason": "具備可對齊比對樣本與足夠交易日；門檻與正式來源選型仍未確認。"})
    else:
        classification.append({"case": "V10 持續觀測與價格交叉比對", "result": "證據不足",
                               "reason": f"對齊樣本 {comparison_section['aligned_samples']}、"
                                         f"進入吻合率分母 {comparison_section['match_rate']['denominator']}、"
                                         f"觀測交易日 {json.dumps(observed, ensure_ascii=False)}；"
                                         f"建議下限為每市場 {THRESHOLDS['minimum_trading_days']} 個完整交易日。"})
    classification.append({
        "case": "報價來源正確性",
        "result": "部分符合" if comparison_section["match_rate"]["denominator"] else "證據不足",
        "reason": comparison_section["note"]})
    limitations = [
        "指標門檻為驗收計畫提出、尚未確認的建議值；報告只標示是否達到建議值，不作為 SLA。",
        "快取回傳不計入來源取得成功；未執行的操作不進入首次／重試成功率分母。",
        "無法從持久化資料獨立判斷行情是否因無成交而變舊，逾時效樣本一律列為需調查。",
        "台股最小報價單位依官方級距由標的類型決定；schema 0003 之前寫入的報價沒有類型，只列精確差異而不判定吻合。",
        "報告產生主機不等於執行 run 的容器；平台證據以 run 的 image_id 與 package_version 為準。",
        "report 不重新抓價；缺漏無法事後補齊。",
        "報告含持股代碼與股數，移交前須依驗收第 7 節處理。",
    ]
    if coverage_section["unsupported"] or coverage_section["unverified"]:
        open_cases.append("名單涵蓋率未達 100%：" + json.dumps(
            coverage_section["unsupported"] + coverage_section["unverified"], ensure_ascii=False))
    if schedule_section is None:
        open_cases.append("本範圍不屬於任何 campaign，沒有預定輪次可重建排程覆蓋率與時效分母。")
    elif schedule_section["not_yet_due"]:
        open_cases.append(f"campaign 尚有 {schedule_section['not_yet_due']} 個未到期的預定機會，觀測尚未結束。")
    if freshness_section is not None and freshness_section["verdict"] == "insufficient_evidence":
        open_cases.append("時效達標率為證據不足：" + freshness_section["verdict_reason"])
    if comparison_section["undetermined_threshold_samples"]:
        open_cases.append(f"{comparison_section['undetermined_threshold_samples']} 筆對齊樣本無法判定最小報價單位。")
    open_cases.append("V01、V02、V03、V05–V08 的功能案例由步驟 1–7 與步驟 9 執行，本報告不判定。")
    return {"scope": scope, "identity": str(identity), "classification": classification,
            "limitations": limitations, "open_cases": open_cases,
            "next_steps": [
                "與使用者確認時效、覆蓋率與比對門檻後重跑報告，再據此判定符合或不符合。",
                "沒有標的類型的舊報價無法判定台股吻合率；需要時以 schema 0003 之後的觀測重跑。",
                "依步驟 9 完成台美股各至少三個完整交易日的盤中觀測，再彙整 V01–V10。",
            ],
            "providers": providers}


def _providers(config):
    section = config.get("providers", {}) if isinstance(config, dict) else {}
    return {"valuation": section.get("valuation", "yahoo"), "comparison": list(section.get("comparison", ()))}


def _poll_seconds(config):
    section = config.get("scheduler", {}) if isinstance(config, dict) else {}
    value = section.get("poll_interval_seconds", 60)
    return value if type(value) is int and value > 0 else 60


def build_run(snapshot, *, as_of, schedule=None, maintenance=None, campaign=None):
    """One run's evidence. Schedule-based denominators need the campaign that planned it."""
    run = snapshot["run"]
    config = run["config_snapshot"] or {}
    providers = _providers(config)
    valuation, comparison = providers["valuation"], tuple(providers["comparison"])
    holdings, cycles = snapshot["holdings"], snapshot["cycles"]
    attempts, quotes = snapshot["fetch_attempts"], snapshot["quotes"]
    markets = {row["id"]: row["market"] for row in cycles}
    groups = opportunities(attempts, markets)
    index = cycle_quote_index(attempts, quotes)
    schedule_section = None if schedule is None else schedule_coverage(schedule, as_of=as_of, maintenance=maintenance)
    freshness_section = None if schedule is None else freshness(
        schedule, as_of=as_of, holdings=holdings, cycle_quotes=index, valuation=valuation)
    comparison_section = price_comparison(index, valuation=valuation, comparison=comparison)
    valuation_section = valuation_check(holdings, cycles, snapshot["valuations"], snapshot["totals"], quotes)
    coverage_section = coverage(holdings, attempts, quotes, valuation=valuation)
    incident_section = incidents(attempts, cycles, snapshot["valuations"], quotes, [run],
                                 schedule or [], as_of=as_of, poll_seconds=_poll_seconds(config))
    overall = aggregate(groups)
    days = trading_days(cycles)
    return {
        "identity": {
            "run_id": str(run["id"]), "campaign_id": str(run["campaign_id"]) if run["campaign_id"] else None,
            "status": run["status"], "started_at": _stamp(run["started_at"]), "ended_at": _stamp(run["ended_at"]),
            "heartbeat_at": _stamp(run["heartbeat_at"]), "recovered_at": _stamp(run["recovered_at"]),
            "package_version": run["package_version"], "image_id": run["image_id"],
            "input_hash": run["input_hash"], "config_hash": run["config_hash"], "config_snapshot": config,
            "providers": providers, "trading_days": days,
            "planned_start": _stamp(campaign["planned_start"]) if campaign else None,
            "planned_end": _stamp(campaign["planned_end"]) if campaign else None,
            "calendar_version": campaign["calendar_version"] if campaign else None,
            "schedule_version": campaign["schedule_version"] if campaign else None,
            "threshold_version": campaign["threshold_version"] if campaign else None,
            "holdings": [{"ticker": row["ticker"], "market": row["market"], "currency": row["currency"],
                          "quantity": _decimal(row["quantity"]), "buy_price": _decimal(row["buy_price"])}
                         for row in sorted(holdings, key=lambda row: (row["market"], row["ticker"]))],
        },
        "volume": {
            "holding_count": len(holdings), "cycles_recorded": len(cycles),
            "cycles_completed": sum(1 for row in cycles if row["status"] == "completed"),
            "scheduled_due": None if schedule_section is None else schedule_section["due"],
            "fetch_opportunities": overall["opportunities"],
            "fetch_operations": overall["operations"],
            "executed_operations": overall["executed_operations"],
            "retry_operations": overall["retry_operations"],
        },
        "metrics": {
            "catalog_coverage": coverage_section["catalog_coverage"],
            "first_attempt_success": overall["first_attempt_success"],
            "retry_success": overall["retry_success"],
            "operation_latency": overall["latency"],
            "schedule_coverage": None if schedule_section is None else schedule_section["including_maintenance"]["coverage"],
            "freshness_rate": None if freshness_section is None else freshness_section["freshness_rate"],
        },
        "coverage": coverage_section,
        "schedule": schedule_section,
        "freshness": freshness_section,
        "by_provider": grouped(groups, lambda group: group["provider"]),
        "by_market": grouped(groups, lambda group: group["market"]),
        "by_ticker": grouped(groups, lambda group: group["ticker"]),
        "incidents": incident_section,
        "price_comparison": comparison_section,
        "valuation_check": valuation_section,
        "conclusions": conclusions(scope="run", identity=run["id"], coverage_section=coverage_section,
                                   schedule_section=schedule_section, freshness_section=freshness_section,
                                   comparison_section=comparison_section, valuation_section=valuation_section,
                                   incident_section=incident_section, days=days, providers=providers),
    }


def run_schedule(schedule, run, *, as_of):
    """This run's own share of the plan: its claimed opportunities plus the gaps in its window."""
    end = min(run["ended_at"] or as_of, as_of)
    return [row for row in schedule
            if row["run_id"] == run["id"]
            or (row["run_id"] is None and run["started_at"] <= row["scheduled_at"] <= end)]


def build_campaign(snapshot, *, as_of):
    """Aggregate every run of one campaign against the single immutable plan."""
    campaign = snapshot["campaign"]
    schedule = snapshot["scheduled_cycles"]
    maintenance = campaign["maintenance_windows"] or []
    config = campaign["config_snapshot"] or {}
    providers = _providers(config)
    valuation, comparison = providers["valuation"], tuple(providers["comparison"])
    runs = [row["run"] for row in snapshot["runs"]]
    holdings = [row for item in snapshot["runs"] for row in item["holdings"]]
    cycles = [row for item in snapshot["runs"] for row in item["cycles"]]
    attempts = [row for item in snapshot["runs"] for row in item["fetch_attempts"]]
    quotes = [row for item in snapshot["runs"] for row in item["quotes"]]
    valuations = [row for item in snapshot["runs"] for row in item["valuations"]]
    totals = [row for item in snapshot["runs"] for row in item["totals"]]
    markets = {row["id"]: row["market"] for row in cycles}
    groups = opportunities(attempts, markets)
    index = cycle_quote_index(attempts, quotes)
    # The campaign list is immutable, so any run's holdings describe the whole campaign.
    campaign_holdings = snapshot["runs"][0]["holdings"] if snapshot["runs"] else []
    schedule_section = schedule_coverage(schedule, as_of=as_of, maintenance=maintenance)
    freshness_section = freshness(schedule, as_of=as_of, holdings=campaign_holdings,
                                 cycle_quotes=index, valuation=valuation)
    comparison_section = price_comparison(index, valuation=valuation, comparison=comparison)
    valuation_section = valuation_check(holdings, cycles, valuations, totals, quotes)
    coverage_section = coverage(campaign_holdings, attempts, quotes, valuation=valuation)
    incident_section = incidents(attempts, cycles, valuations, quotes, runs, schedule,
                                 as_of=as_of, poll_seconds=_poll_seconds(config))
    overall = aggregate(groups)
    days = trading_days(cycles)
    return {
        "identity": {
            "campaign_id": str(campaign["id"]), "status": campaign["status"],
            "planned_start": _stamp(campaign["planned_start"]), "planned_end": _stamp(campaign["planned_end"]),
            "ended_at": _stamp(campaign["ended_at"]),
            "calendar_version": campaign["calendar_version"], "schedule_version": campaign["schedule_version"],
            "threshold_version": campaign["threshold_version"],
            "input_hash": campaign["input_hash"], "config_hash": campaign["config_hash"],
            "config_snapshot": config, "providers": providers,
            "source_instruments": campaign["source_instruments"],
            "trading_days": days,
            "runs": [{"run_id": str(row["id"]), "status": row["status"], "started_at": _stamp(row["started_at"]),
                      "ended_at": _stamp(row["ended_at"]), "recovered_at": _stamp(row["recovered_at"]),
                      "package_version": row["package_version"], "image_id": row["image_id"]}
                     for row in sorted(runs, key=lambda row: (row["started_at"], str(row["id"])))],
            "holdings": [{"ticker": row["ticker"], "market": row["market"], "currency": row["currency"],
                          "quantity": _decimal(row["quantity"]), "buy_price": _decimal(row["buy_price"])}
                         for row in sorted(campaign_holdings, key=lambda row: (row["market"], row["ticker"]))],
        },
        "volume": {
            "holding_count": len(campaign_holdings), "run_count": len(runs),
            "scheduled_total": schedule_section["scheduled_total"], "scheduled_due": schedule_section["due"],
            "cycles_recorded": len(cycles),
            "cycles_completed": sum(1 for row in cycles if row["status"] == "completed"),
            "fetch_opportunities": overall["opportunities"], "fetch_operations": overall["operations"],
            "executed_operations": overall["executed_operations"], "retry_operations": overall["retry_operations"],
        },
        "metrics": {
            "catalog_coverage": coverage_section["catalog_coverage"],
            "first_attempt_success": overall["first_attempt_success"],
            "retry_success": overall["retry_success"],
            "operation_latency": overall["latency"],
            "schedule_coverage": schedule_section["including_maintenance"]["coverage"],
            "schedule_coverage_excluding_maintenance": schedule_section["excluding_maintenance"]["coverage"],
            "freshness_rate": freshness_section["freshness_rate"],
        },
        "coverage": coverage_section,
        "schedule": schedule_section,
        "freshness": freshness_section,
        "by_provider": grouped(groups, lambda group: group["provider"]),
        "by_market": grouped(groups, lambda group: group["market"]),
        "by_ticker": grouped(groups, lambda group: group["ticker"]),
        "incidents": incident_section,
        "price_comparison": comparison_section,
        "valuation_check": valuation_section,
        "conclusions": conclusions(scope="campaign", identity=campaign["id"], coverage_section=coverage_section,
                                   schedule_section=schedule_section, freshness_section=freshness_section,
                                   comparison_section=comparison_section, valuation_section=valuation_section,
                                   incident_section=incident_section, days=days, providers=providers),
        "runs": [build_run(item, as_of=as_of, schedule=run_schedule(schedule, item["run"], as_of=as_of),
                           maintenance=maintenance, campaign=campaign)
                 for item in sorted(snapshot["runs"], key=lambda item: (item["run"]["started_at"], str(item["run"]["id"])))],
    }


def _rate(value):
    if value is None or value.get("rate") is None:
        return "無資料"
    text = f"{value['numerator']}/{value['denominator']}（{value['rate'] * 100:.2f}%）"
    if "meets_threshold" in value:
        text += f"；建議門檻 {value['threshold'] * 100:.0f}%：" + {True: "達到", False: "未達", None: "無法判定"}[value["meets_threshold"]]
    return text


def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def render_markdown(document):
    """Markdown mirrors the JSON; anything the data cannot support stays marked insufficient."""
    body = document["report"]
    identity = body["identity"]
    scope = document["scope"]
    title = identity.get("campaign_id") if scope == "campaign" else identity.get("run_id")
    lines = [f"# 可靠性報告（{scope} {title}）", "",
             f"報告版本 {document['report_version']}；產生時間 {document['generated_at']}；"
             f"統計截止 {document['as_of']}。`report` 不重新抓價。", ""]

    lines += ["## 1. 觀測範圍與版本", ""]
    lines += _table(["項目", "值"], [
        ["scope", scope],
        ["campaign-id", identity.get("campaign_id") or "無（單次 run）"],
        ["run-id", identity.get("run_id") or "多個，見執行清單"],
        ["狀態", identity["status"]],
        ["預定起訖", f"{identity.get('planned_start') or '—'} → {identity.get('planned_end') or '—'}"],
        ["實際起訖", f"{identity.get('started_at') or '—'} → {identity.get('ended_at') or '—'}"],
        ["觀測交易日", json.dumps(identity["trading_days"], ensure_ascii=False)],
        ["估值來源", identity["providers"]["valuation"]],
        ["比較來源", ", ".join(identity["providers"]["comparison"]) or "無"],
        ["package 版本", identity.get("package_version") or "見執行清單"],
        ["image-id", identity.get("image_id") or "見執行清單"],
        ["日曆／排程／門檻版本", f"{identity.get('calendar_version') or '—'} / "
                                f"{identity.get('schedule_version') or '—'} / {identity.get('threshold_version') or '—'}"],
        ["輸入雜湊", identity["input_hash"]],
        ["設定雜湊", identity["config_hash"]],
        ["報告產生主機", f"{document['report_host']['python']} / {document['report_host']['platform']}"],
    ])
    lines += ["", "標的清單：", ""]
    lines += _table(["ticker", "市場", "幣別", "股數"],
                    [[row["ticker"], row["market"], row["currency"], row["quantity"]]
                     for row in identity["holdings"]]) + [""]

    volume = body["volume"]
    lines += ["## 2. 規模", ""]
    lines += _table(["項目", "值"], [[key, "無資料" if value is None else value] for key, value in volume.items()]) + [""]

    metrics = body["metrics"]
    lines += ["## 3. 指標", ""]
    lines += _table(["指標", "值"], [
        ["名單涵蓋率", _rate(metrics["catalog_coverage"])],
        ["首次取得成功率", _rate(metrics["first_attempt_success"])],
        ["重試後成功率", _rate(metrics["retry_success"])],
        ["排程覆蓋率", _rate(metrics["schedule_coverage"])],
        ["時效達標率", _rate(metrics["freshness_rate"])],
        ["操作耗時 p50／p95／max（ms）",
         f"{metrics['operation_latency']['p50_ms']}／{metrics['operation_latency']['p95_ms']}／"
         f"{metrics['operation_latency']['max_ms']}（樣本 {metrics['operation_latency']['samples']}）"],
    ]) + [""]
    for label, section in (("來源", body["by_provider"]), ("市場", body["by_market"]), ("標的", body["by_ticker"])):
        lines += [f"每{label}成功率與耗時：", ""]
        lines += _table([label, "機會", "已執行", "首次成功率", "重試後成功率", "p95(ms)"],
                        [[name, item["opportunities"], item["executed_opportunities"],
                          _rate(item["first_attempt_success"]), _rate(item["retry_success"]),
                          item["latency"]["p95_ms"]] for name, item in section.items()]) + [""]
    if body["schedule"] is None:
        lines += ["排程覆蓋率與時效達標率無法計算：本範圍沒有 campaign 預定輪次。", ""]
    else:
        schedule = body["schedule"]
        lines += ["排程機會（含預定維護窗口）：", ""]
        lines += _table(["範圍", "預定", "已執行", "跳過", "中斷", "缺漏", "覆蓋率"],
                        [["全部", schedule["including_maintenance"]["planned"], schedule["including_maintenance"]["executed"],
                          schedule["including_maintenance"]["skipped"], schedule["including_maintenance"]["interrupted"],
                          schedule["including_maintenance"]["missing"], _rate(schedule["including_maintenance"]["coverage"])],
                         ["排除維護窗口", schedule["excluding_maintenance"]["planned"], schedule["excluding_maintenance"]["executed"],
                          schedule["excluding_maintenance"]["skipped"], schedule["excluding_maintenance"]["interrupted"],
                          schedule["excluding_maintenance"]["missing"], _rate(schedule["excluding_maintenance"]["coverage"])]]
                        + [[f"市場 {market}", item["planned"], item["executed"], item["skipped"], item["interrupted"],
                            item["missing"], _rate(item["coverage"])] for market, item in schedule["by_market"].items()]
                        + [[f"窗口 {kind}", item["planned"], item["executed"], item["skipped"], item["interrupted"],
                            item["missing"], _rate(item["coverage"])] for kind, item in schedule["by_window_type"].items()])
        lines += ["", f"未到期預定機會 {schedule['not_yet_due']}；預定維護窗口 "
                      f"{json.dumps(schedule['maintenance_windows'], ensure_ascii=False)}。", ""]
        fresh = body["freshness"]
        lines += ["時效判定：", ""]
        lines += _table(["項目", "值"], [
            ["合格機會", fresh["qualified_opportunities"]],
            ["符合時效", fresh["outcome"]["fresh"]],
            ["逾時或過舊", fresh["outcome"]["late_or_stale"]],
            ["時間未知", fresh["outcome"]["unknown_time"]],
            ["缺漏", fresh["outcome"]["missing"]],
            ["排除", json.dumps(fresh["excluded"], ensure_ascii=False)],
            ["時效達標率", _rate(fresh["freshness_rate"])],
            ["判定", f"{fresh['verdict']}：{fresh['verdict_reason']}"],
            ["規則", f"宣告延遲 ≤ {fresh['rule']['declared_delay_seconds']} 秒、quote age ≤ "
                     f"{fresh['rule']['quote_age_seconds']} 秒；{fresh['rule']['exclusion_rule']}"],
        ]) + [""]

    incident = body["incidents"]
    lines += ["## 4. 失敗、缺漏、快取與停機", ""]
    lines += _table(["項目", "值"], [
        ["嘗試狀態", json.dumps(incident["attempt_status_counts"], ensure_ascii=False)],
        ["429（rate_limited）", incident["rate_limited_operations"]],
        ["逾時", incident["timeouts"]],
        ["未執行操作", incident["not_executed_operations"]],
        ["缺價估值", f"{incident['missing_valuations']}；原因 {json.dumps(incident['missing_reasons'], ensure_ascii=False)}"],
        ["時間未知報價", incident["unknown_time_quotes"]],
        ["快取使用", json.dumps(incident["cache_usage"], ensure_ascii=False)],
        ["降級估值", incident["degraded_valuations"]],
        ["輪次狀態", json.dumps(incident["cycle_status_counts"], ensure_ascii=False)],
        ["跳過原因", json.dumps(incident["skip_reasons"], ensure_ascii=False)],
        ["恢復紀錄", f"run {len(incident['recovery']['runs_recovered'])}、"
                     f"cycle {incident['recovery']['cycles_recovered']}、"
                     f"attempt {incident['recovery']['attempts_recovered']}、"
                     f"interrupted run {incident['recovery']['interrupted_runs']}"],
    ]) + [""]
    if incident["downtime_windows"]:
        lines += ["停機（依預定機會重建）：", ""]
        lines += _table(["市場", "起", "訖", "缺漏機會", "時長（秒）"],
                        [[row["market"], row["from"], row["to"], row["missing_count"], row["duration_seconds"]]
                         for row in incident["downtime_windows"]]) + [""]
    else:
        lines += ["沒有依預定機會重建出的停機窗口。", ""]

    compare_section = body["price_comparison"]
    lines += ["## 5. 價格比對", ""]
    lines += _table(["項目", "值"], [
        ["比對樣本", compare_section["total_samples"]],
        ["對齊樣本", compare_section["aligned_samples"]],
        ["無法判定門檻樣本", compare_section["undetermined_threshold_samples"]],
        ["未對齊原因", json.dumps(compare_section["unaligned_reasons"], ensure_ascii=False)],
        ["價格吻合率", _rate(compare_section["match_rate"])],
        ["超門檻案例", len(compare_section["over_threshold"])],
    ])
    lines += ["", compare_section["note"], ""]

    check = body["valuation_check"]
    lines += ["## 6. 小計人工核對與完整性", ""]
    lines += _table(["項目", "值"], [
        ["completeness 分布", json.dumps(check["completeness_counts"], ensure_ascii=False)],
        ["重算一致", {True: "是", False: "否"}[bool(check["recomputation_agrees"])]],
        ["不一致項目", json.dumps(check["mismatches"], ensure_ascii=False)],
    ]) + [""]
    for entry in check["manual_check_cycles"]:
        lines += [f"市場 {entry['market']}、輪次 {entry['cycle_id']}（排定 {entry['scheduled_at']}）：", ""]
        lines += _table(["ticker", "股數", "報價", "儲存市值", "重算市值", "顯示值", "品質標記"],
                        [[row["ticker"], row["quantity"], row["price"] or "缺價",
                          row["stored_market_value"] or "無法估值", row["recomputed_market_value"] or "無法估值",
                          row["display"] or "—", "|".join(row["quality_flags"]) or "—"]
                         for row in entry["holdings"]]) + [""]
        lines += _table(["幣別", "completeness", "已估值／總數", "小計（精確）", "小計（顯示）", "總額", "顯示尾差"],
                        [[row["currency"], row["completeness"], f"{row['valued_count']}/{row['holding_count']}",
                          row["stored_known_subtotal"], row["known_subtotal_display"],
                          row["total"] or "null（缺價）", row["display_tail_difference"]]
                         for row in entry["subtotals"]]) + [""]
    lines += [check["note"], ""]

    result = body["conclusions"]
    lines += ["## 7. 結論、限制與未完成項目", ""]
    lines += _table(["案例", "分類", "理由"],
                    [[row["case"], row["result"], row["reason"]] for row in result["classification"]]) + [""]
    lines += ["限制：", ""] + [f"- {item}" for item in result["limitations"]] + [""]
    lines += ["未完成或待確認：", ""] + [f"- {item}" for item in result["open_cases"]] + [""]
    lines += ["建議下一步：", ""] + [f"- {item}" for item in result["next_steps"]] + [""]
    if document["scope"] == "campaign":
        lines += ["## 8. 各 run 摘要", ""]
        lines += _table(["run-id", "狀態", "起", "訖", "已完成輪次", "抓取操作", "重試"],
                        [[row["identity"]["run_id"], row["identity"]["status"], row["identity"]["started_at"],
                          row["identity"]["ended_at"] or "—", row["volume"]["cycles_completed"],
                          row["volume"]["fetch_operations"], row["volume"]["retry_operations"]]
                         for row in body.get("runs", [])]) + [""]
    return "\n".join(lines) + "\n"


def _identity(value, label):
    try:
        return UUID(str(value))
    except ValueError:
        raise ConfigurationError(f"{label} 必須是有效 UUID。") from None


def _target(output_path, scope, identity, generated):
    base = output_path / "reports" / f"{scope}-{identity}"
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    for suffix in ("", *(f"-{number}" for number in range(1, 100))):
        candidate = base / f"{stamp}{suffix}"
        if not candidate.exists():
            return candidate
    raise OSError(f"{base} 已有過多同秒報告目錄。")


def execute(config_path, output_path, *, run_id=None, campaign_id=None, as_of=None, now_fn=None):
    """Produce one reliability report from persisted evidence in a read-only snapshot."""
    if (run_id is None) == (campaign_id is None):
        raise ConfigurationError("report 需要 --run-id 或 --campaign-id 其中之一。")
    scope = "run" if run_id else "campaign"
    identity = _identity(run_id or campaign_id, "--run-id" if run_id else "--campaign-id")
    database = load_database_config(config_path)
    generated = (now_fn or (lambda: datetime.now(UTC)))().astimezone(UTC)
    as_of = generated if as_of is None else as_of.astimezone(UTC)
    with Storage(database) as storage:
        # No collection lock: reporting never blocks or delays a running monitor.
        with storage.report_snapshot():
            try:
                if scope == "run":
                    snapshot = storage.read_run(identity)
                    campaign, schedule = None, None
                    if snapshot["run"]["campaign_id"]:
                        campaign, rows = storage.read_schedule(snapshot["run"]["campaign_id"], as_of=as_of)
                        schedule = run_schedule(rows, snapshot["run"], as_of=as_of)
                    report = build_run(snapshot, as_of=as_of, schedule=schedule, campaign=campaign,
                                       maintenance=campaign["maintenance_windows"] if campaign else None)
                else:
                    report = build_campaign(storage.read_campaign(identity, as_of=as_of), as_of=as_of)
            except ValueError:
                raise ConfigurationError(f"指定的 {scope} 不存在。") from None
    document = {"report_version": REPORT_VERSION, "scope": scope, "identity": str(identity),
                "generated_at": generated.isoformat(), "as_of": as_of.isoformat(),
                "thresholds": THRESHOLDS,
                "report_host": {"python": sys.version.split()[0], "platform": platform.platform(),
                                "note": "報告產生主機，非執行 run 的容器。"},
                "report": report}
    directory = _target(Path(output_path), scope, identity, generated)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "report.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    (directory / "report.md").write_text(render_markdown(document), encoding="utf-8")
    return 0, directory, document

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
import json

import pytest

from stock_quote_fetcher.models import (
    Completeness, FetchResult, FetchStatus, Holding, Instrument, Market, PriceKind,
    QualityFlag, Quote, Session, TimePrecision,
)
from stock_quote_fetcher.valuation import value_holdings


NOW = datetime(2026, 9, 8, 5, tzinfo=UTC)


def holding(ticker="AAPL", quantity="2.5", buy_price="180"):
    return Holding(ticker, Market.US, Decimal(buy_price), Decimal(quantity))


def quote(ticker="AAPL", price="200.10", **changes):
    base = Quote(ticker, ticker, ticker, Market.US, "USD", "fixture", Decimal(price),
                 PriceKind.LAST_TRADE, NOW, NOW, NOW.date(), Session.REGULAR, TimePrecision.SECOND)
    return replace(base, **changes)


def test_fixed_currency_totals_and_cost_independence():
    tw = Holding("2330", Market.TW, Decimal("900"), Decimal("100"))
    quotes = {"2330": quote("2330", "100.25", market=Market.TW, currency="TWD", provider_symbol="2330.TW"),
              "AAPL": quote()}
    report = value_holdings([tw, holding()], quotes)
    assert [(s.currency, s.total) for s in report.summaries] == [
        ("TWD", Decimal("10025.00")), ("USD", Decimal("500.250"))]
    assert all(s.completeness == Completeness.COMPLETE for s in report.summaries)
    changed = value_holdings([replace(tw, buy_price=Decimal("1")), holding(buy_price="999")], quotes)
    assert changed.summaries == report.summaries
    payload = report.to_dict()
    assert "total" not in payload  # No mixed-currency total.
    assert payload["holdings"][0]["ticker"] == "2330"
    assert payload["holdings"][0]["provider_symbol"] == "2330.TW"
    assert payload["summaries"][1]["total_display"] == "500.25"
    json.dumps(payload, allow_nan=False)


def test_precision_above_default_context_and_exact_export():
    digits = "123456789012345678901234567890123456789"
    with localcontext() as context:
        context.prec = 4
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        report = value_holdings([holding(quantity="3")], {"AAPL": quote(price=digits)})
        payload = report.to_dict()
    expected = str(int(digits) * 3)
    assert payload["holdings"][0]["market_value"] == expected
    assert payload["summaries"][0]["total"] == expected
    assert payload["summaries"][0]["total_display"] == expected + ".00"


def test_rounding_occurs_after_summing_exact_values():
    report = value_holdings([holding("A", "1"), holding("B", "1")],
                            {"A": quote("A", "0.005"), "B": quote("B", "0.005")})
    payload = report.to_dict()
    assert [r["market_value_display"] for r in payload["holdings"]] == ["0.01", "0.01"]
    assert payload["summaries"][0]["total"] == "0.010"
    assert payload["summaries"][0]["total_display"] == "0.01"


def test_sum_with_widely_differing_exponents():
    report = value_holdings([holding("A", "1"), holding("B", "1")],
                            {"A": quote("A", "1e40"), "B": quote("B", "1e-40")})
    assert report.to_dict()["summaries"][0]["total"] == "1" + "0" * 40 + "." + "0" * 39 + "1"


@pytest.mark.parametrize("flags,expected", [
    (frozenset(), Completeness.COMPLETE),
    (frozenset({QualityFlag.MARKET_CLOSED}), Completeness.COMPLETE),
    (frozenset({QualityFlag.CACHED, QualityFlag.STALE}), Completeness.DEGRADED),
    (frozenset({QualityFlag.TIME_UNKNOWN}), Completeness.DEGRADED),
])
def test_complete_and_degraded(flags, expected):
    source = quote(quality_flags=flags)
    report = value_holdings([holding()], {"AAPL": source})
    assert report.summaries[0].completeness == expected
    assert report.summaries[0].total == Decimal("500.25")
    assert report.rows[0].quote is source
    assert source.quote_time == NOW


def test_partial_and_unavailable():
    inputs = [holding(), holding("VOO")]
    partial = value_holdings(inputs, {"AAPL": quote()}).summaries[0]
    assert partial.completeness == Completeness.PARTIAL
    assert (partial.known_subtotal, partial.total, partial.missing_count) == (Decimal("500.25"), None, 1)
    unavailable = value_holdings(inputs, {}).to_dict()["summaries"][0]
    assert unavailable["completeness"] == "unavailable"
    assert unavailable["known_subtotal"] == "0"
    assert unavailable["total"] is None and unavailable["total_display"] is None


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "sNaN", "Infinity", "-Infinity"])
def test_bad_prices_never_use_cost_as_fallback(price):
    report = value_holdings([holding()], {"AAPL": quote(price=price)})
    assert report.rows[0].failure_reason == "invalid_price"
    assert report.summaries[0].total is None


@pytest.mark.parametrize("changes,reason", [
    ({"currency": "TWD"}, "currency_mismatch"),
    ({"market": Market.TW}, "instrument_mismatch"),
    ({"ticker": "VOO"}, "instrument_mismatch"),
    ({"quote_time": NOW + timedelta(seconds=6)}, "future_time"),
    ({"price_kind": PriceKind.BAR_CLOSE}, "price_kind_mismatch"),
    ({"session": Session.PRE_MARKET}, "outside_regular_session"),
    ({"session": Session.POST_MARKET}, "outside_regular_session"),
    ({"quality_flags": frozenset({QualityFlag.FUTURE_TIME})}, "future_time"),
])
def test_unusable_quotes(changes, reason):
    report = value_holdings([holding()], {"AAPL": quote(**changes)})
    assert report.rows[0].failure_reason == reason
    assert report.rows[0].market_value is None


def test_time_boundary_unknown_time_and_closed_market():
    assert value_holdings([holding()], {"AAPL": quote(quote_time=NOW + timedelta(seconds=5))}).summaries[0].total
    unknown = value_holdings([holding()], {"AAPL": quote(quote_time=None, session=Session.UNKNOWN)})
    assert unknown.summaries[0].completeness == Completeness.DEGRADED
    assert unknown.to_dict()["holdings"][0]["quote_time"] is None
    closed = value_holdings([holding()], {"AAPL": quote(session=Session.CLOSED, price_kind=PriceKind.CLOSE)})
    assert closed.summaries[0].completeness == Completeness.COMPLETE


def test_partial_keeps_degraded_count():
    report = value_holdings([holding(), holding("VOO")],
                            {"AAPL": quote(quality_flags=frozenset({QualityFlag.CACHED}))})
    assert report.summaries[0].completeness == Completeness.PARTIAL
    assert report.summaries[0].degraded_count == 1


def test_models_preserve_mapping_and_failure_separation():
    symbols = {"yahoo": "2330.TW"}
    instrument = Instrument("tw2330", "2330", Market.TW, "TWD", symbols)
    symbols["yahoo"] = "other"
    assert instrument.provider_symbols["yahoo"] == "2330.TW"
    assert FetchResult("AAPL", "fixture", FetchStatus.SUCCESS, quote()).quote
    assert FetchResult("AAPL", "fixture", FetchStatus.TIMEOUT, error="timeout").quote is None
    with pytest.raises(ValueError):
        FetchResult("AAPL", "fixture", FetchStatus.TIMEOUT, quote(), "timeout")
    with pytest.raises(ValueError):
        FetchResult("VOO", "fixture", FetchStatus.SUCCESS, quote())
    with pytest.raises(ValueError):
        quote(received_at=NOW.replace(tzinfo=None))


def test_float_model_fields_rejected():
    with pytest.raises(TypeError):
        replace(quote(), price=1.1)
    with pytest.raises(TypeError):
        Holding("AAPL", Market.US, Decimal("1"), 1.5)


def test_empty_and_duplicate_valuation_input_rejected():
    for rows in ([], [holding(), holding()]):
        with pytest.raises(ValueError):
            value_holdings(rows, {})


@pytest.mark.parametrize("changes", [
    {"session": "unrecognized"}, {"price_kind": "adjusted_close"},
    {"time_precision": "unrecognized"}, {"quality_flags": {"unrecognized"}},
])
def test_unknown_quality_values_cannot_silently_be_complete(changes):
    with pytest.raises(ValueError):
        quote(**changes)


def test_string_enums_are_normalized():
    source = quote(session="closed", quality_flags={"market_closed"})
    assert source.session is Session.CLOSED
    assert value_holdings([holding()], {"AAPL": source}).to_dict()["summaries"][0]["completeness"] == "complete"

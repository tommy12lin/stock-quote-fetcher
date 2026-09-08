"""Exact offline valuation of already-selected quotes; no source switching."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import (
    Context, Decimal, Inexact, MAX_EMAX, MIN_EMIN, ROUND_HALF_UP, Rounded, localcontext,
)
from typing import Mapping, Sequence

from stock_quote_fetcher.models import (
    Completeness, Holding, PriceKind, QualityFlag, Quote, Session, TimePrecision,
)


def exact_context(precision: int) -> Context:
    context = Context(prec=precision, Emax=MAX_EMAX, Emin=MIN_EMIN)
    context.traps[Inexact] = True
    context.traps[Rounded] = True
    return context


def exact_product(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(exact_context(len(left.as_tuple().digits) + len(right.as_tuple().digits))):
        return left * right


def exact_sum(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    exponent = min(value.as_tuple().exponent for value in values)
    highest = max(value.adjusted() for value in values)
    precision = max(1, highest - exponent + 1) + len(str(len(values)))
    with localcontext(exact_context(precision)):
        return sum(values[1:], values[0])


def display_amount(value: Decimal) -> str:
    # Display rounding is intentional and independent of the caller's context.
    context = Context(prec=max(1, value.adjusted() + 1) + 3, rounding=ROUND_HALF_UP,
                      Emax=MAX_EMAX, Emin=MIN_EMIN)
    with localcontext(context):
        return format(value.quantize(Decimal("0.01")), "f")


@dataclass(frozen=True)
class HoldingValuation:
    holding: Holding
    quote: Quote | None
    market_value: Decimal | None
    quality_flags: frozenset[QualityFlag]
    failure_reason: str | None = None

    @property
    def degraded(self) -> bool:
        return self.market_value is not None and bool(self.quality_flags - {QualityFlag.MARKET_CLOSED})


@dataclass(frozen=True)
class CurrencySummary:
    currency: str
    known_subtotal: Decimal
    total: Decimal | None
    holding_count: int
    valued_count: int
    missing_count: int
    degraded_count: int
    completeness: Completeness


@dataclass(frozen=True)
class ValuationReport:
    rows: tuple[HoldingValuation, ...]
    summaries: tuple[CurrencySummary, ...]

    def to_dict(self) -> dict:
        """JSON-ready output: exact Decimal strings plus separately rounded display."""
        from zoneinfo import ZoneInfo
        rows = []
        for row in self.rows:
            holding, quote = row.holding, row.quote
            rows.append({
                "ticker": holding.ticker,
                "market": holding.market.value,
                "currency": holding.currency,
                "buy_price": format(holding.buy_price, "f"),
                "quantity": format(holding.quantity, "f"),
                "provider": quote.provider if quote else None,
                "provider_symbol": quote.provider_symbol if quote else None,
                "price": format(quote.price, "f") if quote else None,
                "price_kind": quote.price_kind.value if quote else None,
                "quote_time": quote.quote_time.isoformat() if quote and quote.quote_time else None,
                "received_at": quote.received_at.isoformat() if quote else None,
                "quote_time_local": quote.quote_time.astimezone(ZoneInfo('Asia/Taipei' if holding.market == 'TW' else 'America/New_York')).isoformat() if quote and quote.quote_time else None,
                "trading_date": quote.trading_date.isoformat() if quote and quote.trading_date else None,
                "session": quote.session.value if quote else None,
                "time_precision": quote.time_precision.value if quote else None,
                "declared_delay_seconds": quote.declared_delay_seconds if quote else None,
                "market_value": format(row.market_value, "f") if row.market_value is not None else None,
                "market_value_display": display_amount(row.market_value) if row.market_value is not None else None,
                "quality_flags": sorted(flag.value for flag in row.quality_flags),
                "failure_reason": row.failure_reason,
            })
        return {
            "holdings": rows,
            "summaries": [{
                "currency": summary.currency,
                "known_subtotal": format(summary.known_subtotal, "f"),
                "known_subtotal_display": display_amount(summary.known_subtotal),
                "total": format(summary.total, "f") if summary.total is not None else None,
                "total_display": display_amount(summary.total) if summary.total is not None else None,
                "holding_count": summary.holding_count,
                "valued_count": summary.valued_count,
                "missing_count": summary.missing_count,
                "degraded_count": summary.degraded_count,
                "completeness": summary.completeness.value,
            } for summary in self.summaries],
        }


def value_holding(holding: Holding, quote: Quote | None, future_tolerance: timedelta) -> HoldingValuation:
    if quote is None:
        return HoldingValuation(holding, None, None, frozenset(), "missing_quote")
    flags = set(quote.quality_flags)
    if quote.quote_time is None or quote.time_precision in (TimePrecision.UNKNOWN, TimePrecision.DAY):
        flags.add(QualityFlag.TIME_UNKNOWN)
    if quote.quote_time is not None and quote.quote_time - quote.received_at > future_tolerance:
        flags.add(QualityFlag.FUTURE_TIME)
    if quote.session == Session.UNKNOWN:
        flags.add(QualityFlag.SESSION_UNKNOWN)
    if quote.session == Session.CLOSED:
        flags.add(QualityFlag.MARKET_CLOSED)
    if quote.currency != holding.currency:
        flags.add(QualityFlag.CURRENCY_MISMATCH)
    if quote.price_kind == PriceKind.BAR_CLOSE:
        # Acceptance of bar data requires a later, explicit source-quality policy.
        flags.add(QualityFlag.PRICE_KIND_MISMATCH)
    reason = None
    if quote.ticker != holding.ticker or quote.market != holding.market:
        reason = "instrument_mismatch"
    elif not quote.price.is_finite() or quote.price <= 0:
        reason = "invalid_price"
    elif QualityFlag.CURRENCY_MISMATCH in flags:
        reason = "currency_mismatch"
    elif QualityFlag.FUTURE_TIME in flags:
        reason = "future_time"
    elif QualityFlag.PRICE_KIND_MISMATCH in flags:
        reason = "price_kind_mismatch"
    elif quote.session in (Session.PRE_MARKET, Session.POST_MARKET):
        reason = "outside_regular_session"
    value = exact_product(holding.quantity, quote.price) if reason is None else None
    return HoldingValuation(holding, quote, value, frozenset(flags), reason)


def value_holdings(
    holdings: Sequence[Holding],
    quotes: Mapping[str, Quote],
    *,
    future_tolerance: timedelta = timedelta(seconds=5),
) -> ValuationReport:
    """Value quotes keyed by input ticker. Cache verification/selection belongs upstream.

    Calendar-based staleness and provider mapping are not inferred here. The caller
    supplies those quality flags; cached quotes keep their original timestamps.
    """
    if not holdings or len({holding.ticker for holding in holdings}) != len(holdings):
        raise ValueError("Valuation requires nonempty, unique holdings.")
    if future_tolerance < timedelta(0):
        raise ValueError("Future tolerance cannot be negative.")
    rows = tuple(value_holding(holding, quotes.get(holding.ticker), future_tolerance) for holding in holdings)
    summaries = []
    for currency in sorted({row.holding.currency for row in rows}):
        group = [row for row in rows if row.holding.currency == currency]
        values = [row.market_value for row in group if row.market_value is not None]
        missing = len(group) - len(values)
        degraded = sum(row.degraded for row in group)
        if not values:
            completeness = Completeness.UNAVAILABLE
        elif missing:
            completeness = Completeness.PARTIAL
        elif degraded:
            completeness = Completeness.DEGRADED
        else:
            completeness = Completeness.COMPLETE
        subtotal = exact_sum(values)
        summaries.append(CurrencySummary(
            currency, subtotal, None if missing else subtotal, len(group), len(values),
            missing, degraded, completeness,
        ))
    return ValuationReport(rows, tuple(summaries))

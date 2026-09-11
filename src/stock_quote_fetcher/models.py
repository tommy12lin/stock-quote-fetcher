"""Shared, provider-independent records. No database or network imports."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class Market(StrEnum):
    TW = "TW"
    US = "US"

    @property
    def currency(self) -> str:
        return "TWD" if self == Market.TW else "USD"


class FetchStatus(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    PROVIDER_ERROR = "provider_error"
    INVALID_PAYLOAD = "invalid_payload"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    INTERRUPTED = "interrupted"


class QualityFlag(StrEnum):
    CACHED = "cached"
    STALE = "stale"
    TIME_UNKNOWN = "time_unknown"
    FRESHNESS_UNKNOWN = "freshness_unknown"
    FUTURE_TIME = "future_time"
    MARKET_CLOSED = "market_closed"
    CURRENCY_MISMATCH = "currency_mismatch"
    SESSION_UNKNOWN = "session_unknown"
    PRICE_KIND_MISMATCH = "price_kind_mismatch"


class PriceKind(StrEnum):
    LAST_TRADE = "last_trade"
    CLOSE = "close"
    BAR_CLOSE = "bar_close"


class Session(StrEnum):
    REGULAR = "regular"
    CLOSED = "closed"
    UNKNOWN = "unknown"
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"


class TimePrecision(StrEnum):
    SECOND = "second"
    MILLISECOND = "millisecond"
    MICROSECOND = "microsecond"
    MINUTE = "minute"
    DAY = "day"
    UNKNOWN = "unknown"


class Completeness(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


def require_decimal(value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError("Numeric model fields require Decimal, never float.")


@dataclass(frozen=True)
class Holding:
    ticker: str
    market: Market
    buy_price: Decimal
    quantity: Decimal
    source_line: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", Market(self.market))
        for value in (self.buy_price, self.quantity):
            require_decimal(value)
            if not value.is_finite() or value <= 0:
                raise ValueError("Holding price and quantity must be finite and positive.")
        if self.market == Market.TW and self.quantity != self.quantity.to_integral_value():
            raise ValueError("Taiwan holdings require whole shares.")

    @property
    def currency(self) -> str:
        return self.market.currency


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    ticker: str  # Normalized input ticker, not a provider symbol.
    market: Market
    currency: str
    provider_symbols: Mapping[str, str] = field(default_factory=dict)
    exchange: str | None = None
    asset_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", Market(self.market))
        object.__setattr__(self, "provider_symbols", MappingProxyType(dict(self.provider_symbols)))


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone.")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Quote:
    instrument_id: str
    ticker: str
    provider_symbol: str
    market: Market
    currency: str
    provider: str
    price: Decimal
    price_kind: PriceKind
    quote_time: datetime | None
    received_at: datetime
    trading_date: date | None
    session: Session
    time_precision: TimePrecision
    declared_delay_seconds: int | None = None
    quality_flags: frozenset[QualityFlag] = field(default_factory=frozenset)
    # Official security type of the instrument; drives the Taiwan tick-size table in reports.
    asset_type: str | None = None

    def __post_init__(self) -> None:
        # Invalid Decimal prices can be retained as evidence, but never valued.
        require_decimal(self.price)
        if self.asset_type not in (None, "stock", "etf"):
            raise ValueError("Quote asset_type must be the official stock or etf category.")
        object.__setattr__(self, "market", Market(self.market))
        object.__setattr__(self, "price_kind", PriceKind(self.price_kind))
        object.__setattr__(self, "session", Session(self.session))
        object.__setattr__(self, "time_precision", TimePrecision(self.time_precision))
        object.__setattr__(self, "received_at", utc_timestamp(self.received_at))
        if self.quote_time is not None:
            object.__setattr__(self, "quote_time", utc_timestamp(self.quote_time))
        object.__setattr__(self, "quality_flags", frozenset(QualityFlag(flag) for flag in self.quality_flags))


@dataclass(frozen=True)
class FetchResult:
    instrument_id: str
    provider: str
    status: FetchStatus
    quote: Quote | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", FetchStatus(self.status))
        if self.status == FetchStatus.SUCCESS:
            if self.quote is None or self.error is not None:
                raise ValueError("Successful fetch requires a quote and no error.")
        elif self.quote is not None or not self.error:
            raise ValueError("Failed fetch requires an error and no quote; cache is separate.")
        if self.quote is not None and (
            self.quote.instrument_id != self.instrument_id or self.quote.provider != self.provider
        ):
            raise ValueError("FetchResult must match the quote instrument and provider.")

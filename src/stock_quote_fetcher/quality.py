"""Calendar-aware quote checks; conservative uncertainty is not provider failure."""

from dataclasses import replace
from datetime import timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from stock_quote_fetcher.models import Market, PriceKind, QualityFlag as F, Session, TimePrecision


def timezone(market):
    return ZoneInfo('Asia/Taipei' if market == Market.TW else 'America/New_York')


@lru_cache(maxsize=8)
def calendar(market, year):
    import exchange_calendars as xc
    return xc.get_calendar('XTAI' if market == Market.TW else 'XNYS',
                           start=f'{year-1}-01-01', end=f'{year+1}-12-31')


def bounds(market, day):
    cal = calendar(market, day.year)
    if not cal.is_session(str(day)):
        return None
    return tuple(x.to_pydatetime() for x in cal.session_open_close(str(day)))


def assess(quote, *, as_of=None, poll_seconds=60):
    now = as_of or quote.received_at
    flags = set(quote.quality_flags) - {F.MARKET_CLOSED, F.STALE}
    local_day = now.astimezone(timezone(quote.market)).date()
    today = bounds(quote.market, local_day)
    opened = today is not None and today[0] <= now <= today[1]
    session = quote.session
    if session not in {Session.PRE_MARKET,Session.POST_MARKET,Session.UNKNOWN}:
        session = Session.REGULAR if opened else Session.CLOSED
    if not opened:
        flags.add(F.MARKET_CLOSED)
    if quote.currency != quote.market.currency:
        flags.add(F.CURRENCY_MISMATCH)
    if quote.price_kind == PriceKind.BAR_CLOSE:
        flags.add(F.PRICE_KIND_MISMATCH)
    if session == Session.UNKNOWN:
        flags.add(F.SESSION_UNKNOWN)
    stamp = quote.quote_time
    trading_day = quote.trading_date
    if stamp is None or quote.time_precision in {TimePrecision.UNKNOWN,TimePrecision.DAY}:
        flags.add(F.TIME_UNKNOWN)
    if stamp is not None:
        if stamp > quote.received_at + timedelta(seconds=5):
            flags.add(F.FUTURE_TIME)
        trading_day = stamp.astimezone(timezone(quote.market)).date()
        traded = bounds(quote.market,trading_day)
        if traded is None or not traded[0] <= stamp <= traded[1] + timedelta(seconds=5):
            # A regular-market field outside the calendar needs investigation.
            flags.add(F.SESSION_UNKNOWN)
            session = Session.UNKNOWN
        delay = quote.declared_delay_seconds
        if delay is None:
            flags.add(F.FRESHNESS_UNKNOWN)  # timestamp exists, delay is unverified
        else:
            if delay > 1200:
                flags.add(F.STALE)
            reference = now - timedelta(seconds=delay)
            ref_day = reference.astimezone(timezone(quote.market)).date()
            cal = calendar(quote.market, ref_day.year)
            label = cal.date_to_session(str(ref_day), direction='previous')
            opening, closing = (x.to_pydatetime() for x in cal.session_open_close(label))
            if reference < opening:
                label = cal.previous_session(label)
                closing = cal.session_close(label).to_pydatetime()
            expected = min(reference,closing)
            if stamp < expected - timedelta(seconds=poll_seconds+10):
                flags.add(F.STALE)
    return replace(quote, session=session, trading_date=trading_day, quality_flags=frozenset(flags))

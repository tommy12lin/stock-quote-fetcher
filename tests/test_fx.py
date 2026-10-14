"""U5 exchange rates: offline normalization, the worker boundary, and the P&L definition."""
from datetime import UTC, datetime
from decimal import Decimal
import json
import subprocess

import pytest

from stock_quote_fetcher import fx
from stock_quote_fetcher.dashboard import calculate
from stock_quote_fetcher.models import Quote
from stock_quote_fetcher.web_input import validate_rows

STAMP = datetime(2026, 10, 13, 6, 51, 49, tzinfo=UTC)


def payload(**changes):
    # The fields TWD=X returned on 2026-10-13, as the worker whitelists them.
    return {'symbol': 'TWD=X', 'currency': 'TWD', 'quoteType': 'CURRENCY', 'regularMarketPrice': 32.138,
            'regularMarketTime': int(STAMP.timestamp()), 'exchangeDataDelayedBy': 0,
            'exchangeTimezoneName': 'Europe/London', 'marketState': 'REGULAR'} | changes


def test_usd_twd_normalizes_to_the_pair_asked_for():
    rate = fx.normalize('USD', 'TWD', payload(), STAMP)
    assert (rate.base_currency, rate.quote_currency, rate.rate) == ('USD', 'TWD', Decimal('32.138'))
    assert rate.provider == 'yahoo' and rate.provider_symbol == 'TWD=X' and rate.rate_kind == 'market'
    assert rate.quote_time == STAMP and rate.received_at == STAMP


@pytest.mark.parametrize('changes,reason', [
    ({'symbol': 'JPY=X'}, 'symbol_mismatch'),
    # An equity or ETF answer under the requested symbol is not an exchange rate.
    ({'quoteType': 'EQUITY'}, 'quote_type_mismatch'),
    # 1 USD in TWD must be quoted in TWD; anything else is the wrong direction or pair.
    ({'currency': 'USD'}, 'currency_mismatch'),
    ({'currency': None}, 'currency_mismatch'),
    ({'regularMarketPrice': 0}, 'price'),
    ({'regularMarketPrice': None}, 'price'),
    ({'regularMarketPrice': 'NaN'}, 'price'),
])
def test_anything_else_is_rejected(changes, reason):
    with pytest.raises(ValueError, match=reason):
        fx.normalize('USD', 'TWD', payload(**changes), STAMP)


def test_bid_and_ask_are_not_used():
    """On 2026-10-13 TWD=X reported 32.138 against an ask of 32.016."""
    rate = fx.normalize('USD', 'TWD', payload(bid=31.916, ask=32.016), STAMP)
    assert rate.rate == Decimal('32.138')


def test_only_the_checked_pair_is_offered():
    with pytest.raises(ValueError, match='unsupported_pair'):
        fx.yahoo_symbol('JPY', 'TWD')


class Done:
    def __init__(self, response, returncode=0):
        self.stdout, self.returncode = json.dumps(response), returncode


def test_fetch_passes_the_timeout_to_the_worker(monkeypatch):
    seen = {}
    def run(args, *, input, capture_output, text, timeout):
        seen['request'], seen['timeout'] = json.loads(input), timeout
        return Done({'status': 'success', 'payload': payload(), 'received_at': STAMP.isoformat()})
    monkeypatch.setattr(subprocess, 'run', run)
    rate, reason = fx.fetch('USD', 'TWD', 7)
    assert reason is None and rate.rate == Decimal('32.138')
    assert seen['timeout'] == 7 and seen['request']['symbol'] == 'TWD=X' and seen['request']['timeout'] == 7


@pytest.mark.parametrize('outcome,reason', [
    (subprocess.TimeoutExpired('worker', 7), 'timeout'),
    (Done({}, returncode=1), 'worker_failed'),
    (Done({'status': 'rate_limited', 'reason': 'rate_limited', 'received_at': STAMP.isoformat()}), 'rate_limited'),
    (Done({'status': 'success', 'payload': payload(currency='USD'), 'received_at': STAMP.isoformat()}), 'invalid_payload'),
])
def test_fetch_failures_return_a_reason_never_a_rate(monkeypatch, outcome, reason):
    def run(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(subprocess, 'run', run)
    assert fx.fetch('USD', 'TWD', 7) == (None, reason)


def test_unrealized_profit_is_the_original_currency_profit_at_the_latest_rate():
    """U5 decision 1: P&L is worked out in the holding's own currency, then converted at
    the newest rate, i.e. what selling everything now would add up to in TWD. It leaves
    out what the rate did to the principal since purchase."""
    stamp = datetime(2026, 9, 8, 14, tzinfo=UTC)
    quotes = {t: Quote(t, t, t, m, c, 'yahoo', Decimal(p), 'last_trade', stamp, stamp, stamp.date(), 'regular', 'second')
              for t, m, c, p in [('2330', 'TW', 'TWD', '100'), ('AAPL', 'US', 'USD', '10.5')]}
    holdings = validate_rows([{'ticker': '2330', 'quantity': '10', 'buy_price': '80'},
                              {'ticker': 'AAPL', 'quantity': '2.5', 'buy_price': '8.25'}])
    rate = Decimal('32.138')
    result = calculate(holdings, quotes, rate)
    # Rows show each holding's P&L in its own currency: 10 x (100 - 80), 2.5 x (10.5 - 8.25).
    assert [r['profit'] for r in result['rows']] == ['200.00', '5.63']
    # 200 + 5.625 x 32.138 = 380.77625, from the exact AAPL figure, not the rounded 5.63.
    assert result['profit'] == '380.78'
    assert result['cost'] == '1462.85'  # 800 + 20.625 x 32.138 = 1462.84625: cost moves with the rate

"""Exchange rates fetched with the quotes (U5); there is no manually entered rate.

The source is Yahoo. Bank of Taiwan board rates were the first choice, but every
non-browser request got a bot challenge page instead of data (2026-10-13), and that
challenge is not to be worked around. See docs/feature-roadmap.md.
"""
from dataclasses import dataclass
from datetime import datetime
import json
import subprocess
import sys

from stock_quote_fetcher.providers import positive, timestamp

PROVIDER = 'yahoo'


@dataclass(frozen=True)
class FxRate:
    base_currency: str
    quote_currency: str
    rate: object
    provider: str
    provider_symbol: str
    quote_time: datetime | None
    received_at: datetime
    rate_kind: str = 'market'


def yahoo_symbol(base, quote):
    # Only USD/TWD ('TWD=X') has been fetched and checked (2026-10-13). Yahoo names a
    # USD-based pair by its quote currency alone.
    if base != 'USD':
        raise ValueError('unsupported_pair')
    return f'{quote}=X'


def normalize(base, quote, payload, received_at):
    """Raises ValueError unless the payload is exactly the pair that was asked for."""
    symbol = yahoo_symbol(base, quote)
    if payload.get('symbol') != symbol:
        raise ValueError('symbol_mismatch')
    if payload.get('quoteType') != 'CURRENCY':
        raise ValueError('quote_type_mismatch')
    if payload.get('currency') != quote:
        raise ValueError('currency_mismatch')
    # regularMarketPrice, never a bid/ask average: on 2026-10-13 TWD=X reported a price
    # above its own ask, so bid and ask are not trusted until that is explained.
    return FxRate(base, quote, positive(payload.get('regularMarketPrice')), PROVIDER, symbol,
                  timestamp(payload.get('regularMarketTime')), received_at)


def fetch(base, quote, timeout):
    """One isolated provider call. Returns (FxRate, None) or (None, reason)."""
    request = {'provider': PROVIDER, 'symbol': yahoo_symbol(base, quote), 'timeout': timeout,
               'company_ca_file': '', 'relaxed': False}
    try:
        process = subprocess.run([sys.executable, '-m', 'stock_quote_fetcher.provider_worker'],
                                 input=json.dumps(request), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, 'timeout'
    if process.returncode != 0:
        return None, 'worker_failed'
    try:
        response = json.loads(process.stdout)
        if response['status'] != 'success':
            return None, str(response['status'])
        return normalize(base, quote, response['payload'], datetime.fromisoformat(response['received_at'])), None
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError):
        return None, 'invalid_payload'

"""Isolated provider I/O. stdout is a small, whitelisted machine response only."""

from contextlib import redirect_stdout, redirect_stderr
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
import io
import json
import logging
import os
import ssl
import sys

URLS = {
    'finnhub': 'https://finnhub.io/api/v1/quote',
    'twse': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    'tpex': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes',
}
YAHOO_FIELDS = ('symbol','currency','quoteType','regularMarketPrice','regularMarketTime',
                'exchangeDataDelayedBy','exchangeTimezoneName','marketState')
MAX_BYTES = 12 * 1024 * 1024


def retry_after(value):
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, min(seconds, 86400)) if seconds < float('inf') else 86400


def fetch(request):
    provider, symbol = request['provider'], request['symbol']
    if provider == 'yahoo':
        import yfinance as yf
        info = yf.Ticker(symbol).get_info()
        return {'status':'success', 'payload':{k: info.get(k) for k in YAHOO_FIELDS}}
    if provider == 'finnhub' and not os.environ.get('FINNHUB_API_KEY','').strip():
        return {'status':'provider_error','reason':'missing_api_key'}
    import httpx
    context = ssl.create_default_context()
    if request.get('company_ca_file'):
        context.load_verify_locations(cafile=request['company_ca_file'])
    if request.get('relaxed'):
        context.verify_flags &= ~getattr(ssl,'VERIFY_X509_STRICT',0)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    headers = {'Accept':'application/json'}
    params = None
    if provider == 'finnhub':
        headers['X-Finnhub-Token'] = os.environ['FINNHUB_API_KEY'].strip()
        params = {'symbol':symbol}
    with httpx.Client(verify=context, timeout=request['timeout'], follow_redirects=False) as client:
        with client.stream('GET',URLS[provider],params=params,headers=headers) as response:
            code = response.status_code
            if code != 200:
                status = ('rate_limited' if code == 429 else 'unsupported_symbol' if code == 404
                          else 'network_error' if code >= 500 else 'provider_error')
                return {'status':status,'reason':f'http_{code}', 'retry_after':retry_after(response.headers.get('retry-after'))}
            if 'application/json' not in response.headers.get('content-type','').lower():
                return {'status':'invalid_payload','reason':'content_type'}
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    return {'status':'invalid_payload','reason':'response_too_large'}
                chunks.append(chunk)
    payload = json.loads(b''.join(chunks), parse_float=str)
    if provider == 'finnhub':
        if not isinstance(payload,dict):
            return {'status':'invalid_payload','reason':'schema'}
        payload = {k:payload.get(k) for k in ('c','t')}
    else:
        field = 'Code' if provider == 'twse' else 'SecuritiesCompanyCode'
        price = 'ClosingPrice' if provider == 'twse' else 'Close'
        if not isinstance(payload,list):
            return {'status':'invalid_payload','reason':'schema'}
        rows = [row for row in payload if isinstance(row,dict) and row.get(field) == symbol]
        if len(rows) != 1:
            return {'status':'unsupported_symbol','reason':'missing_or_ambiguous'}
        payload = {k:rows[0].get(k) for k in (field,price,'Date')}
    return {'status':'success','payload':payload}


def main():
    request = json.load(sys.stdin)
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = fetch(request)
    except Exception as exc:
        # Never serialize third-party error text, URLs, response bodies or headers.
        name = type(exc).__name__.lower()
        status = ('rate_limited' if 'ratelimit' in name else 'timeout' if 'timeout' in name
                  else 'invalid_payload' if isinstance(exc,(ValueError,TypeError,KeyError)) else 'network_error')
        result = {'status':status,'reason':status}
    result['received_at'] = datetime.now(UTC).isoformat()
    print(json.dumps(result,allow_nan=False))


if __name__ == '__main__':
    main()

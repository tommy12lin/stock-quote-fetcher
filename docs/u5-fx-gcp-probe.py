"""U5 GCP egress probe: can Cloud Run fetch Yahoo's TWD=X, and how long does it take?

Runs inside the image the service already uses (35743d47289f), as a temporary Cloud Run
Job with no database and no secrets. That image has no fx module, but fx.fetch is only
this request through stock_quote_fetcher.provider_worker, which has not changed since
35743d4 (nor have providers.py, uv.lock or the Dockerfile), so this is the same call.
The checks below mirror fx.normalize.

Shipped base64 in FX_PROBE and started with
    python -c "exec(__import__('base64').b64decode(__import__('os').environ['FX_PROBE']))"
Prints one JSON line per step to stdout, for Cloud Logging. Read only: no writes anywhere.
"""
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal

ROUNDS = 3
REQUEST = {'provider': 'yahoo', 'symbol': 'TWD=X', 'timeout': 10, 'company_ca_file': '', 'relaxed': False}


def emit(**fields):
    print(json.dumps({'probe': 'u5-fx', 'at': datetime.now(UTC).isoformat(), **fields}, ensure_ascii=False), flush=True)


def check(payload):
    problems = []
    if payload.get('symbol') != 'TWD=X':
        problems.append('symbol_mismatch')
    if payload.get('quoteType') != 'CURRENCY':
        problems.append('quote_type_mismatch')
    if payload.get('currency') != 'TWD':
        problems.append('currency_mismatch')
    try:
        if not Decimal(str(payload.get('regularMarketPrice'))) > 0:
            problems.append('price')
    except ArithmeticError:
        problems.append('price')
    return problems


def main():
    emit(step='start', python=sys.version.split()[0], rounds=ROUNDS)
    for number in range(1, ROUNDS + 1):
        started = time.monotonic()
        try:
            process = subprocess.run([sys.executable, '-m', 'stock_quote_fetcher.provider_worker'],
                                     input=json.dumps(REQUEST), capture_output=True, text=True, timeout=REQUEST['timeout'])
            elapsed = round(time.monotonic() - started, 3)
            response = json.loads(process.stdout) if process.returncode == 0 else {'status': 'worker_failed'}
        except subprocess.TimeoutExpired:
            elapsed, response = round(time.monotonic() - started, 3), {'status': 'timeout'}
        payload = response.get('payload') or {}
        emit(step='fetch', round=number, elapsed_seconds=elapsed, status=response.get('status'),
             reason=response.get('reason'), received_at=response.get('received_at'),
             price=payload.get('regularMarketPrice'), quote_time=payload.get('regularMarketTime'),
             currency=payload.get('currency'), quote_type=payload.get('quoteType'),
             problems=check(payload) if response.get('status') == 'success' else None)
        time.sleep(2)
    # Outside the worker's whitelist: bid and ask, to see whether the price-above-ask seen
    # on 2026-10-13 from the company network also appears from GCP. Not used by the code.
    try:
        import yfinance as yf
        info = yf.Ticker('TWD=X').get_info()
        emit(step='bid_ask', price=info.get('regularMarketPrice'), bid=info.get('bid'), ask=info.get('ask'),
             quote_time=info.get('regularMarketTime'))
    except Exception as exc:
        emit(step='bid_ask', error=type(exc).__name__)
    emit(step='end')


main()

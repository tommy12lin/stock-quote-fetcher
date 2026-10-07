"""US intraday reference (plan section 10): Nasdaq.com last sale, recorded from this machine.

Not part of the service, and not run on GCP: what is checked is the price GCP got from Yahoo.
Yahoo labels most US quotes "Nasdaq Real Time Price", so for those this is a same-source check
(our pipeline relays Nasdaq faithfully), not independent proof; see the plan.

  record  python -m scripts.c76_nasdaq record --out output/intraday-us-1007/nasdaq.jsonl --minutes 90 --symbols aapl:stocks,voo:etf
  trades  python -m scripts.c76_nasdaq trades --out output/intraday-us-1007/trades.jsonl --symbol AAPL --from-time 10:00

record polls the watchlist endpoint, which answers at most 20 symbols per request, so the
list is split. trades saves one raw page of the Nasdaq Last Sale trade list per call.
"""
import argparse
from datetime import UTC, datetime
import json
import sys
import time

WATCHLIST_URL = 'https://api.nasdaq.com/api/quote/watchlist'
TRADES_URL = 'https://api.nasdaq.com/api/quote/{symbol}/realtime-trades'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
BATCH = 20  # 10-07: 21 symbols in one request came back as 20


def _client():
    import httpx
    return httpx.Client(timeout=10, headers=HEADERS)


def record(out, *, symbols, minutes, interval, client=None, clock=time.monotonic, sleep=time.sleep):
    """One line per request. Errors are recorded and polling goes on: a gap is evidence too."""
    client = client or _client()
    batches = [symbols[i:i + BATCH] for i in range(0, len(symbols), BATCH)]
    end = clock() + minutes * 60
    while True:
        for batch in batches:
            line = {'fetched_at': datetime.now(UTC).isoformat()}
            try:
                response = client.get(WATCHLIST_URL, params=[('symbol', s) for s in batch])
                line['http_status'] = response.status_code
                line['data'] = response.json().get('data')
            except Exception as exc:  # noqa: BLE001 - every failure is written down, none stops the record
                line['error'] = f'{type(exc).__name__}: {exc}'
            line['requested'] = batch
            out.write(json.dumps(line, ensure_ascii=False) + '\n')
            out.flush()
        if clock() + interval > end:
            return
        sleep(interval)


def trades(out, *, symbol, from_time, limit, offset=0, client=None):
    client = client or _client()
    line = {'fetched_at': datetime.now(UTC).isoformat(), 'symbol': symbol, 'from_time': from_time,
            'limit': limit, 'offset': offset}
    try:
        response = client.get(TRADES_URL.format(symbol=symbol),
                              params={'limit': limit, 'offset': offset, 'fromTime': from_time})
        line['http_status'] = response.status_code
        line['data'] = response.json().get('data')
    except Exception as exc:  # noqa: BLE001
        line['error'] = f'{type(exc).__name__}: {exc}'
    out.write(json.dumps(line, ensure_ascii=False) + '\n')
    out.flush()
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(prog='c76_nasdaq')
    sub = parser.add_subparsers(dest='command', required=True)
    rec = sub.add_parser('record')
    rec.add_argument('--out', required=True)
    rec.add_argument('--minutes', type=float, required=True)
    rec.add_argument('--interval', type=float, default=5)
    rec.add_argument('--symbols', required=True, help='e.g. aapl:stocks,voo:etf')
    tr = sub.add_parser('trades')
    tr.add_argument('--out', required=True)
    tr.add_argument('--symbol', required=True)
    tr.add_argument('--from-time', required=True)
    tr.add_argument('--limit', type=int, default=100)
    tr.add_argument('--offset', type=int, default=0)
    args = parser.parse_args(argv)
    with open(args.out, 'a', encoding='utf-8') as f:
        if args.command == 'record':
            if args.interval < 5:
                parser.error('--interval 不得小於 5 秒。')
            symbols = [s.strip().replace(':', '|') for s in args.symbols.split(',') if s.strip()]
            record(f, symbols=symbols, minutes=args.minutes, interval=args.interval)
        else:
            trades(f, symbol=args.symbol, from_time=args.from_time, limit=args.limit, offset=args.offset)
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""C7-6 R2 reference: TWSE MIS intraday snapshots, and their comparison with the probe.

Not part of the service, and not run on GCP: the reference may come from any network,
since what is checked is the price GCP got from Yahoo, not whether MIS is reachable.

Yahoo declares a 20-minute delay for Taiwan (docs/poc-validation.md), so a quote fetched
at T carries a trade from about T-20min. Comparing it with MIS at T compares two different
trades. Instead, `record` keeps MIS snapshots from well before the Job runs, and `compare`
looks for the snapshot whose last-trade time equals the Yahoo quote_time exactly.

  record   python -m scripts.c76_mis record --out output/c76/r2-mis.jsonl --minutes 40
  compare  python -m scripts.c76_mis compare --probe output/c76/r2.jsonl --mis output/c76/r2-mis.jsonl

A Yahoo quote with no snapshot at its exact trade time is reported as unaligned, with the
neighbouring snapshots for investigation; it never enters the matched count.
"""
import argparse
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
import sys
import time

from stock_quote_fetcher.reporting import tick_size

# The Taiwan half of c76_probe.FIXED: MIS channel and official asset type (for the tick).
TW_FIXED = {'2330': ('tse', 'stock'), '2317': ('tse', 'stock'), '0050': ('tse', 'etf'),
            '6488': ('otc', 'stock'), '3529': ('otc', 'stock'), '006201': ('otc', 'etf')}
MIS_URL = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
KEEP = ('c', 'ex', 'd', 't', 'tlong', 'z', 'y')


def record(out, *, minutes, interval, client=None, clock=time.monotonic, sleep=time.sleep):
    """One line per poll. Errors are recorded and polling goes on: a gap is evidence too."""
    import httpx
    client = client or httpx.Client(timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
    channels = '|'.join(f'{ex}_{code}.tw' for code, (ex, _) in TW_FIXED.items())
    end = clock() + minutes * 60
    while True:
        line = {'fetched_at': datetime.now(UTC).isoformat()}
        try:
            response = client.get(MIS_URL, params={'ex_ch': channels, 'json': '1', 'delay': '0'})
            line['http_status'] = response.status_code
            body = response.json()
            line['rtcode'] = body.get('rtcode')
            line['quotes'] = [{k: m.get(k) for k in KEEP} for m in body.get('msgArray', [])]
        except Exception as exc:  # noqa: BLE001 - every failure is written down, none stops the record
            line['error'] = f'{type(exc).__name__}: {exc}'
        out.write(json.dumps(line, ensure_ascii=False) + '\n')
        out.flush()
        if clock() + interval > end:
            return
        sleep(interval)


def _price(text):
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError):
        return None  # MIS shows '-' when the snapshot carries no trade
    return value if value.is_finite() and value > 0 else None


def snapshots(mis_lines):
    """ticker -> {trade time in ms: MIS price or None}, from every successful poll."""
    seen = {}
    for line in mis_lines:
        for q in line.get('quotes') or []:
            if q.get('c') in TW_FIXED and str(q.get('tlong', '')).isdigit():
                seen.setdefault(q['c'], {})[int(q['tlong'])] = _price(q.get('z'))
    return seen


def compare(probe_lines, mis_lines):
    """One result per successful Taiwan attempt of the fixed list."""
    seen = snapshots(mis_lines)
    results = []
    for line in probe_lines:
        if line.get('kind') != 'attempt' or line.get('market') != 'TW' or line.get('ticker') not in TW_FIXED:
            continue
        if line.get('status') != 'success' or line.get('price') is None or line.get('quote_time') is None:
            continue
        ticker, price = line['ticker'], Decimal(str(line['price']))
        stamp = datetime.fromisoformat(line['quote_time'])
        ms = int(stamp.timestamp() * 1000)
        result = {'ticker': ticker, 'run_id': line.get('run_id'), 'quote_time': stamp.isoformat(),
                  'yahoo_price': str(price)}
        times = seen.get(ticker, {})
        if ms in times and times[ms] is not None:
            reference = times[ms]
            tick = tick_size('TW', reference, TW_FIXED[ticker][1])
            diff = price - reference
            result.update(aligned=True, mis_price=str(reference), diff=str(diff), tick=str(tick),
                          within_tick=abs(diff) <= tick)
        else:
            before = max((t for t in times if t < ms), default=None)
            after = min((t for t in times if t > ms), default=None)
            reason = ('mis_no_price_at_trade_time' if ms in times else
                      'before_recording' if before is None else
                      'after_recording' if after is None else 'no_snapshot_at_trade_time')
            result.update(aligned=False, reason=reason, neighbours=[
                {'mis_time': datetime.fromtimestamp(t / 1000, UTC).isoformat(),
                 'mis_price': None if times[t] is None else str(times[t])}
                for t in (before, after) if t is not None])
        results.append(result)
    return results


def _jsonl(path):
    """Plain JSONL, or the probe's "C76 {...}" lines with anything else in between."""
    with open(path, encoding='utf-8') as f:
        lines = [l.strip().removeprefix('C76 ') for l in f]
    return [json.loads(l) for l in lines if l.startswith('{')]


def main(argv=None, out=sys.stdout):
    parser = argparse.ArgumentParser(prog='c76_mis')
    sub = parser.add_subparsers(dest='command', required=True)
    rec = sub.add_parser('record')
    rec.add_argument('--out', required=True)
    rec.add_argument('--minutes', type=float, required=True)
    # MIS's own page polls every 5 s (userDelay 5000); going faster risks a block.
    rec.add_argument('--interval', type=float, default=5)
    cmp_ = sub.add_parser('compare')
    cmp_.add_argument('--probe', required=True)
    cmp_.add_argument('--mis', required=True)
    args = parser.parse_args(argv)
    if args.command == 'record':
        if args.interval < 5:
            parser.error('--interval 不得小於 5 秒。')
        with open(args.out, 'a', encoding='utf-8') as f:
            record(f, minutes=args.minutes, interval=args.interval)
        return 0
    for result in compare(_jsonl(args.probe), _jsonl(args.mis)):
        out.write(json.dumps(result, ensure_ascii=False) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())

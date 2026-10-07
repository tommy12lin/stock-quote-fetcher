import json
from io import StringIO

import httpx

from scripts.c76_nasdaq import record


def test_record_splits_into_batches_of_twenty_and_keeps_failures():
    # 10-07: the watchlist endpoint answered 20 of 21 symbols, silently dropping the last one.
    seen = []

    def handler(request):
        symbols = request.url.params.get_list('symbol')
        seen.append(symbols)
        if len(seen) == 2:
            raise httpx.ConnectTimeout('timed out')
        return httpx.Response(200, json={'data': [{'symbol': s.split('|')[0].upper()} for s in symbols]})

    symbols = [f's{i}|stocks' for i in range(20)] + ['voo|etf']
    now = [0.0]
    out = StringIO()
    record(out, symbols=symbols, minutes=0.1, interval=5,
           client=httpx.Client(transport=httpx.MockTransport(handler)),
           clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    lines = [json.loads(l) for l in out.getvalue().splitlines()]
    # 6 s at 5 s intervals: two polls, each of two requests.
    assert [len(s) for s in seen] == [20, 1, 20, 1]
    assert len(lines) == 4
    assert lines[1]['requested'] == ['voo|etf'] and 'error' in lines[1]
    assert [d['symbol'] for d in lines[2]['data']][-1] == 'S19'

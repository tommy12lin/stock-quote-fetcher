"""C7-6 R2 reference: MIS snapshots are matched to Yahoo quotes by exact trade time only.

Offline: the probe's attempt lines and MIS polls are written by hand in the shapes the real
scripts produce. What this cannot show is whether real Yahoo and MIS trade times coincide.
"""
from datetime import UTC, datetime, timedelta
from io import StringIO
import json

import httpx
import pytest

from scripts import c76_mis
from scripts.c76_mis import compare, main, record

# 2026-09-29 09:40:05 Taipei, a Taiwan trading day.
TRADE = datetime(2026, 9, 29, 1, 40, 5, tzinfo=UTC)


def attempt(ticker, price, when=TRADE, **overrides):
    # c76_probe emits with json.dumps(default=str): datetimes become "YYYY-MM-DD HH:MM:SS+00:00".
    row = {'kind': 'attempt', 'run_id': 'run-1', 'market': 'TW', 'ticker': ticker, 'provider': 'yahoo',
           'status': 'success', 'price': price, 'quote_time': str(when)}
    return {**row, **overrides}


def poll(*quotes):
    return {'fetched_at': '2026-09-29T02:00:00+00:00', 'rtcode': '0000',
            'quotes': [{'c': c, 'tlong': str(int(t.timestamp() * 1000)), 'z': z} for c, t, z in quotes]}


def test_aligned_trade_time_compares_the_price_against_one_tick():
    results = compare([attempt('2330', '2475.00'), attempt('2317', '251.5')],
                      [poll(('2330', TRADE, '2475.0000'), ('2317', TRADE, '250.5000'))])
    assert [(r['ticker'], r['aligned'], r['diff'], r['tick'], r['within_tick']) for r in results] == [
        ('2330', True, '0.0000', '5', True),
        # 250.5 -> 251.5 is two ticks of 0.5: over the investigation threshold.
        ('2317', True, '1.0000', '0.5', False)]


def test_etf_uses_the_etf_tick_table():
    [result] = compare([attempt('0050', '112.45')], [poll(('0050', TRADE, '112.4000'))])
    # A stock at 112.4 would tick 0.5; the ETF table says 0.05, so this is exactly one tick.
    assert (result['tick'], result['within_tick']) == ('0.05', True)


def test_a_neighbouring_snapshot_with_the_same_price_is_still_unaligned():
    earlier, later = TRADE - timedelta(seconds=5), TRADE + timedelta(seconds=5)
    [result] = compare([attempt('2330', '2475.00')],
                       [poll(('2330', earlier, '2475.0000')), poll(('2330', later, '2480.0000'))])
    assert result['aligned'] is False
    assert result['reason'] == 'no_snapshot_at_trade_time'
    assert 'within_tick' not in result
    assert [n['mis_price'] for n in result['neighbours']] == ['2475.0000', '2480.0000']


def test_unaligned_reasons_distinguish_coverage_from_missing_price():
    after = TRADE + timedelta(seconds=30)
    results = compare([attempt('2330', '2475'), attempt('6488', '948'), attempt('3529', '3230')],
                      [poll(('2330', after, '2480.0000'), ('6488', TRADE, '-'),
                            ('3529', TRADE - timedelta(seconds=30), '3230.0000'))])
    assert [(r['ticker'], r['reason']) for r in results] == [
        ('2330', 'before_recording'), ('6488', 'mis_no_price_at_trade_time'), ('3529', 'after_recording')]


def test_only_successful_taiwan_attempts_of_the_fixed_list_are_compared():
    lines = [attempt('2330', None, status='rate_limited'), attempt('AAPL', '250', market='US'),
             attempt('1101', '40'), {'kind': 'batch', 'run_id': 'run-1'}, attempt('006201', '46.17')]
    [result] = compare(lines, [poll(('006201', TRADE, '46.1700'))])
    assert (result['ticker'], result['aligned'], result['within_tick']) == ('006201', True, True)


def test_main_reads_the_raw_probe_log_and_the_mis_record(tmp_path):
    probe = tmp_path / 'r2.jsonl'
    probe.write_text('unrelated log line\nC76 ' + json.dumps(attempt('2330', '2475')) + '\n\n', encoding='utf-8')
    mis = tmp_path / 'r2-mis.jsonl'
    mis.write_text(json.dumps(poll(('2330', TRADE, '2475.0000'))) + '\n', encoding='utf-8')
    out = StringIO()
    assert main(['compare', '--probe', str(probe), '--mis', str(mis)], out) == 0
    assert json.loads(out.getvalue())['aligned'] is True


def test_record_writes_every_poll_including_failures_and_stops_on_time():
    calls = []

    def handler(request):
        calls.append(request.url.params['ex_ch'])
        if len(calls) == 2:
            return httpx.Response(503, text='blocked')
        return httpx.Response(200, json={'rtcode': '0000', 'msgArray': [
            {'c': '2330', 'ex': 'tse', 'd': '20260929', 't': '09:40:05', 'tlong': '1790646005000',
             'z': '2475.0000', 'y': '2470.0000', 'v': '1'}]})

    now = [0.0]
    out = StringIO()
    record(out, minutes=0.25, interval=5, client=httpx.Client(transport=httpx.MockTransport(handler)),
           clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    lines = [json.loads(l) for l in out.getvalue().splitlines()]
    # 15 s at 5 s intervals: polls at 0, 5, 10, 15.
    assert len(lines) == 4
    assert lines[1]['http_status'] == 503 and 'error' in lines[1]
    assert lines[2]['quotes'] == [{'c': '2330', 'ex': 'tse', 'd': '20260929', 't': '09:40:05',
                                   'tlong': '1790646005000', 'z': '2475.0000', 'y': '2470.0000'}]
    assert calls[0] == 'tse_2330.tw|tse_2317.tw|tse_0050.tw|otc_6488.tw|otc_3529.tw|otc_006201.tw'


def test_record_refuses_polling_faster_than_mis_itself(tmp_path, monkeypatch):
    # pytest.fail is a BaseException: if the guard is gone, this fails at once instead of polling MIS.
    monkeypatch.setattr(c76_mis, 'record', lambda *a, **k: pytest.fail('record ran despite --interval 1'))
    with pytest.raises(SystemExit):
        main(['record', '--out', str(tmp_path / 'x.jsonl'), '--minutes', '1', '--interval', '1'])
    assert not (tmp_path / 'x.jsonl').exists()

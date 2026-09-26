"""C7-6 R4 evidence: every expectation is checked on its own, and nothing missing passes.

Offline: probe lines are written by hand in the shapes c76_probe emits, and the official
responses in the shapes TWSE STOCK_DAY and TPEx tradingStock return. What this cannot show
is what Yahoo actually returns from GCP on a weekend; that is R4 itself.
"""
from io import StringIO
import json

from scripts.c76_report import TW_DATE, anomalies, assess, main, reference_closes

CLOSES = {'2330': '2475.00', '2317': '250.50', '0050': '112.40', '6488': '948.00', '3529': '3230.00', '006201': '46.17'}
US = {'AAPL': '255.10', 'MSFT': '510.20', 'BRK.B': '480.30', 'VOO': '600.40', 'QQQ': '590.50'}


def attempt(ticker, close, **overrides):
    # c76_probe emits with json.dumps(default=str): Decimal and datetime become strings.
    market = 'US' if ticker in US else 'TW'
    row = {'kind': 'attempt', 'run_id': f'run-{market}', 'market': market, 'ticker': ticker, 'provider': 'yahoo',
           'attempt_number': 1, 'status': 'success', 'error_code': None, 'elapsed_ms': 800,
           'adapter': {'executed': True, 'retry_after_seconds': None}, 'price': f'{close}00',
           'price_kind': 'close', 'quote_time': '2026-09-24 05:30:00+00:00' if market == 'TW' else '2026-09-25 20:00:00+00:00',
           'trading_date': '2026-09-24' if market == 'TW' else '2026-09-25', 'session': 'closed',
           'declared_delay_seconds': 1200 if market == 'TW' else None,
           'quality_flags': ['market_closed'], 'valuation_flags': ['market_closed']}
    return {**row, **overrides}


def view(ticker, close, **overrides):
    return {'kind': 'view', 'ticker': ticker, 'price': f'{close}00', 'quality_flags': ['cached', 'market_closed'], **overrides}


def weekend(**changes):
    """A clean R4 log; `changes` maps ticker -> (attempt overrides, view overrides) or None to drop it."""
    lines = [{'kind': 'start', 'mode': 'refresh', 'at': '2026-09-26 02:00:00+00:00', 'instance': 'i-1',
              'deadline_seconds': 110, 'max_tickers': 0},
             {'kind': 'portfolio', 'revision': 7, 'spec': 'fixed', 'tickers': list(CLOSES) + list(US)},
             {'kind': 'manifest', 'runs': ['run-TW', 'run-US'], 'refresh_jobs': ['job-1']},
             {'kind': 'job', 'job_id': 'job-1', 'owned': True, 'status': 'succeeded', 'message': '完成',
              'refresh_started_at': '2026-09-26 02:00:01+00:00', 'elapsed_seconds': 14.2}]
    for ticker, price in {**CLOSES, **US}.items():
        if ticker in changes and changes[ticker] is None:
            continue
        a, v = changes.get(ticker, ({}, {}))
        lines += [attempt(ticker, price, **a), view(ticker, price, **v)]
    return lines


def by_ticker(lines, closes=None):
    return {r['ticker']: r for r in assess(lines, reference(closes))}


def reference(closes=None):
    from decimal import Decimal
    return {t: Decimal(p) for t, p in (closes or CLOSES).items()}


def test_a_clean_weekend_meets_every_expectation_and_still_leaves_us_prices_unproven():
    results = by_ticker(weekend())
    assert all(not r['problems'] for r in results.values()), {t: r['problems'] for t, r in results.items()}
    assert {r['price_check'] for t, r in results.items() if t in CLOSES} == {'equal'}
    # Passing Taiwan says nothing about the US: no comparison source was set (2026-09-25).
    assert {r['price_check'] for t, r in results.items() if t in US} == {'insufficient_evidence'}


def test_each_flag_layer_must_carry_market_closed_on_its_own():
    results = by_ticker(weekend(**{'2330': ({}, {'quality_flags': ['cached']}),
                                   'AAPL': ({'valuation_flags': None}, {}),
                                   '6488': ({'quality_flags': ['stale']}, {})}))
    assert results['2330']['problems'] == ['view 旗標沒有 market_closed']
    assert results['AAPL']['problems'] == ['valuation 旗標缺漏']
    assert results['6488']['problems'] == ['stored 旗標沒有 market_closed']


def test_prices_are_compared_exactly_with_one_tick_only_as_the_investigation_threshold():
    results = by_ticker(weekend(**{'0050': ({'price': '112.4500'}, {'price': '112.4500'}),
                                   '2330': ({'price': '2485.0000'}, {'price': '2485.0000'})}))
    # The ETF table ticks 0.05 at 112.4 (a stock would tick 0.5): one tick off, still not equal.
    assert (results['0050']['price_check'], results['0050']['tick']) == ('within_tick', '0.05')
    assert results['0050']['problems'] == ['價格與官方收盤差 0.0500（一個 tick 為 0.05）']
    assert (results['2330']['price_check'], results['2330']['tick']) == ('exceeds_tick', '5')


def test_trading_date_is_the_previous_session_of_each_market():
    results = by_ticker(weekend(**{'2317': ({'trading_date': '2026-09-25'}, {}),
                                   'MSFT': ({'trading_date': '2026-09-24'}, {})}))
    # Taiwan was closed on 09-25, so a Taiwan quote dated 09-25 is wrong even though New York traded.
    assert results['2317']['problems'] == ['trading_date 為 2026-09-25，預期 2026-09-24']
    assert results['MSFT']['problems'] == ['trading_date 為 2026-09-24，預期 2026-09-25']


def test_missing_attempts_references_and_page_prices_are_reported_not_passed():
    closes = {t: p for t, p in CLOSES.items() if t != '006201'}
    results = by_ticker(weekend(**{'3529': None, 'VOO': ({}, {'price': '599.9000'})}), closes)
    assert results['3529']['price_check'] == 'no_price'
    assert results['3529']['problems'][:2] == ['沒有嘗試紀錄', 'stored 旗標缺漏']
    assert results['006201']['price_check'] == 'no_reference'
    assert '沒有官方收盤參考值' in results['006201']['problems']
    assert results['VOO']['problems'] == ['頁面價格 599.9000 與本次抓到的 600.4000 不同']


def test_a_retried_ticker_is_judged_on_its_success_and_the_failure_is_listed():
    lines = weekend()
    failed = attempt('AAPL', '255.10', status='rate_limited', error_code='rate_limited', price=None,
                     adapter={'reason': 'http_429', 'retry_after_seconds': 30, 'executed': True})
    lines.insert(lines.index(next(l for l in lines if l.get('ticker') == 'AAPL')), failed)
    results = by_ticker(lines)
    assert results['AAPL']['attempts'] == 2 and not results['AAPL']['problems']
    assert anomalies(lines) == [{'ticker': 'AAPL', 'attempt_number': 1, 'status': 'rate_limited',
                                 'error_code': 'rate_limited', 'reason': 'http_429', 'retry_after_seconds': 30,
                                 'elapsed_ms': 800}]


def twse(ticker, rows):
    return {'stat': 'OK', 'fields': ['日期', '成交股數', '收盤價', '漲跌價差'],
            'data': [[d, '1,000', c, '+0.00'] for d, c in rows]}


def tpex(ticker, rows):
    return {'tables': [{'fields': ['日 期', '成交張數', '收盤', '漲跌'], 'data': [[d, '61', c, '0.00'] for d, c in rows]}],
            'code': ticker, 'stat': 'ok'}


def test_reference_takes_the_row_of_the_date_not_the_latest_row(tmp_path):
    (tmp_path / 'twse-2330-202609.json').write_text(json.dumps(twse('2330', [
        ('115/09/23', '2,500.00'), ('115/09/24', '2,475.00'), ('115/09/29', '2,490.00')])), encoding='utf-8')
    (tmp_path / 'tpex-006201-20260924.json').write_text(json.dumps(tpex('006201', [
        ('115/09/24', '46.17'), ('115/09/29', '46.50')])), encoding='utf-8')
    (tmp_path / 'tpex-3529-20260924.json').write_text(json.dumps(tpex('3529', [('115/09/23', '3,305.00')])),
                                                        encoding='utf-8')
    closes = reference_closes(tmp_path, TW_DATE)
    # 3529 has no 09-24 row and no neighbouring day stands in for it; the others have no file.
    assert {t: str(c) for t, c in closes.items()} == {'2330': '2475.00', '006201': '46.17'}


def test_main_renders_the_log_as_cloud_logging_hands_it_over(tmp_path):
    ref = tmp_path / 'ref'
    ref.mkdir()
    for ticker, price in CLOSES.items():
        if ticker in ('2330', '2317', '0050'):
            (ref / f'twse-{ticker}-202609.json').write_text(json.dumps(twse(ticker, [('115/09/24', price)])), encoding='utf-8')
        else:
            (ref / f'tpex-{ticker}-20260924.json').write_text(json.dumps(tpex(ticker, [('115/09/24', price)])), encoding='utf-8')
    probe = tmp_path / 'r4.jsonl'
    lines = weekend(**{'QQQ': ({'quality_flags': []}, {})})
    probe.write_text('Starting probe\n' + ''.join('C76 ' + json.dumps(l, ensure_ascii=False) + '\n' for l in lines),
                     encoding='utf-8')
    out = StringIO()
    assert main(['--probe', str(probe), '--reference', str(ref), '--execution', 'c76-source-probe-abcde'], out) == 0
    text = out.getvalue()
    assert '### R4　雙邊休市（2026-09-26 台北）' in text
    assert '| execution | c76-source-probe-abcde |' in text
    assert '（未提供，須由執行前的 `describe` 補上）' in text
    assert '| **portfolio revision**（最後 `reset` 用） | 7 |' in text
    assert '`{"runs": ["run-TW", "run-US"], "refresh_jobs": ["job-1"]}`' in text
    assert '符合全部預期：10／11 檔' in text and '台股價格等於官方收盤：6／6 檔' in text
    assert '| QQQ | 1 | （無） |' in text

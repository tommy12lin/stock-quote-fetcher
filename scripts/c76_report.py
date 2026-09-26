"""C7-6 R4 evidence: the probe log set against the official closes, as Markdown.

Not part of the service, and not run on GCP. R4 runs on a weekend with both markets
closed, so every fixed ticker should carry market_closed, and each Taiwan price should
equal the previous trading day's official close (docs/cloud-phase-1-plan.md, C7-6).

  python -m scripts.c76_report --probe output/c76/r4.jsonl --reference output/c76/r4-reference \
      --execution c76-source-probe-xxxxx --digest sha256:...

The execution name and image digest come from gcloud, not from the log, so they are
arguments. The output is a draft for docs/cloud-C7-evidence.md: it states what the log
shows and what each expectation was, and never turns a missing value into a pass.
"""
import argparse
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from scripts.c76_mis import TW_FIXED, _jsonl
from scripts.c76_probe import FIXED
from stock_quote_fetcher.reporting import tick_size

TAIPEI = ZoneInfo('Asia/Taipei')
# Previous regular sessions before the weekend of 2026-09-26: Taiwan was closed on 09-25
# (Mid-Autumn Festival), New York was not. See the plan's C7-6 "R4 執行準備".
TW_DATE, US_DATE = date(2026, 9, 24), date(2026, 9, 25)
CLOSED = 'market_closed'


def _roc(text):
    """'115/09/24' -> date(2026, 9, 24)."""
    year, month, day = (int(p) for p in text.strip().split('/'))
    return date(year + 1911, month, day)


def _decimal(text):
    try:
        value = Decimal(str(text).replace(',', ''))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def reference_closes(directory, on):
    """ticker -> official close on `on`, from the raw TWSE STOCK_DAY / TPEx tradingStock files.

    A ticker whose file is missing, or has no row for that date, is simply absent: the
    comparison then reports no reference instead of borrowing a neighbouring day.
    """
    closes = {}
    for ticker, (channel, _) in TW_FIXED.items():
        if channel == 'tse':
            found = sorted(Path(directory).glob(f'twse-{ticker}-*.json'))
            tables = [json.loads(p.read_text(encoding='utf-8')) for p in found]
            column = '收盤價'
        else:
            found = sorted(Path(directory).glob(f'tpex-{ticker}-*.json'))
            tables = [t for p in found for t in json.loads(p.read_text(encoding='utf-8')).get('tables', [])]
            column = '收盤'
        for table in tables:
            fields = [f.replace(' ', '') for f in table.get('fields', [])]
            if column not in fields or '日期' not in fields:
                continue
            for row in table.get('data', []):
                if _roc(row[fields.index('日期')]) == on:
                    closes[ticker] = _decimal(row[fields.index(column)])
    return closes


def _flags(value):
    return sorted(value) if isinstance(value, list) else None


def _local(text):
    if not text:
        return None
    stamp = datetime.fromisoformat(str(text))
    return stamp.astimezone(TAIPEI).strftime('%m-%d %H:%M:%S')


def assess(lines, closes, *, tw_date=TW_DATE, us_date=US_DATE):
    """One verdict per fixed ticker. Every expectation is checked separately and named."""
    attempts = [l for l in lines if l.get('kind') == 'attempt']
    views = {l['ticker']: l for l in lines if l.get('kind') == 'view'}
    results = []
    for ticker in FIXED:
        market = 'TW' if ticker in TW_FIXED else 'US'
        mine = [a for a in attempts if a.get('ticker') == ticker]
        quoted = [a for a in mine if a.get('status') == 'success' and a.get('price') is not None]
        last = quoted[-1] if quoted else None
        view = views.get(ticker)
        problems = []
        if not mine:
            problems.append('沒有嘗試紀錄')
        elif last is None:
            problems.append('沒有成功取得報價')
        layers = {'stored': _flags(last.get('quality_flags')) if last else None,
                  'valuation': _flags(last.get('valuation_flags')) if last else None,
                  'view': _flags(view.get('quality_flags')) if view else None}
        for layer, flags in layers.items():
            if flags is None:
                problems.append(f'{layer} 旗標缺漏')
            elif CLOSED not in flags:
                problems.append(f'{layer} 旗標沒有 {CLOSED}')
        expected_date = tw_date if market == 'TW' else us_date
        got_date = last.get('trading_date') if last else None
        if last is not None and got_date != expected_date.isoformat():
            problems.append(f'trading_date 為 {got_date}，預期 {expected_date}')
        if view is not None and last is not None and _decimal(view.get('price')) != _decimal(last.get('price')):
            problems.append(f'頁面價格 {view.get("price")} 與本次抓到的 {last.get("price")} 不同')
        result = {'ticker': ticker, 'market': market, 'attempts': len(mine), 'layers': layers,
                  'trading_date': got_date, 'expected_date': expected_date.isoformat(),
                  'price': last.get('price') if last else None,
                  'price_kind': last.get('price_kind') if last else None,
                  'quote_time': last.get('quote_time') if last else None,
                  'session': last.get('session') if last else None}
        if market == 'US':
            result['price_check'] = 'insufficient_evidence'
        elif closes.get(ticker) is None:
            result['price_check'] = 'no_reference'
            problems.append('沒有官方收盤參考值')
        elif last is None:
            result['price_check'] = 'no_price'
        else:
            reference, price = closes[ticker], _decimal(last['price'])
            tick = tick_size('TW', reference, TW_FIXED[ticker][1])
            diff = price - reference
            result.update(reference=str(reference), diff=str(diff), tick=str(tick))
            if diff == 0:
                result['price_check'] = 'equal'
            else:
                result['price_check'] = 'within_tick' if abs(diff) <= tick else 'exceeds_tick'
                problems.append(f'價格與官方收盤差 {diff}（一個 tick 為 {tick}）')
        result['problems'] = problems
        results.append(result)
    return results


def anomalies(lines):
    """Every attempt that did not succeed. retry-after is only read off a non-200 response
    (provider_worker), so a successful attempt never carries one."""
    found = []
    for a in (l for l in lines if l.get('kind') == 'attempt'):
        adapter = a.get('adapter') if isinstance(a.get('adapter'), dict) else {}
        if a.get('status') != 'success':
            found.append({'ticker': a.get('ticker'), 'attempt_number': a.get('attempt_number'),
                          'status': a.get('status'), 'error_code': a.get('error_code'),
                          'reason': adapter.get('reason'), 'retry_after_seconds': adapter.get('retry_after_seconds'),
                          'elapsed_ms': a.get('elapsed_ms')})
    return found


def _cell(value):
    if value is None:
        return '—'
    if isinstance(value, list):
        return ', '.join(value) if value else '（無）'
    return str(value).replace('|', '\\|')


def _table(header, rows):
    out = ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    out += ['| ' + ' | '.join(_cell(c) for c in row) + ' |' for row in rows]
    return out


def _one(lines, kind):
    found = [l for l in lines if l.get('kind') == kind]
    return found[0] if len(found) == 1 else None


CHECK_TEXT = {'equal': '相等', 'within_tick': '差距在一個 tick 內，但不相等', 'exceeds_tick': '**超過一個 tick**',
              'no_price': '無價格', 'no_reference': '無參考值', 'insufficient_evidence': '證據不足（未設比較來源）'}


def render(lines, closes, *, execution=None, digest=None):
    start, portfolio = _one(lines, 'start'), _one(lines, 'portfolio')
    manifest, job = _one(lines, 'manifest'), _one(lines, 'job')
    errors = [l for l in lines if l.get('kind') == 'error']
    results = assess(lines, closes)
    at = datetime.fromisoformat(str(start['at'])) if start else None
    out = [f'### R4　雙邊休市（{at.astimezone(TAIPEI):%Y-%m-%d} 台北）' if at else '### R4　雙邊休市',
           '', '> 本段由 `scripts/c76_report.py` 從 `output/c76/r4.jsonl` 產生，貼入前須人工核對。', '']
    out += _table(['項目', '值'], [
        ['execution', execution or '（未提供，須由 `gcloud run jobs executions list` 補上）'],
        ['映像 digest', digest or '（未提供，須由執行前的 `describe` 補上）'],
        ['腳本開始', f'{at.astimezone(UTC):%H:%M:%S}Z（台北 {at.astimezone(TAIPEI):%m-%d %H:%M:%S}）' if at else None],
        ['instance', start.get('instance') if start else None],
        ['deadline／max_tickers', f'{start.get("deadline_seconds")}／{start.get("max_tickers")}' if start else None],
        ['更新工作', f'`{job["job_id"]}`，`{job["status"]}`，{job["message"]}' if job else None],
        ['`refresh()` 耗時', f'{job["elapsed_seconds"]} 秒' if job else None],
        ['**portfolio revision**（最後 `reset` 用）', portfolio.get('revision') if portfolio else None],
        ['**manifest**（併入清除清單）', f'`{json.dumps({k: manifest[k] for k in ("runs", "refresh_jobs")})}`' if manifest else None],
        ['錯誤行', len(errors)]])
    for e in errors:
        out.append(f'\n錯誤：`{json.dumps(e, ensure_ascii=False)}`')

    batches = [l for l in lines if l.get('kind') == 'batch']
    out += ['', '**各批**', '']
    out += _table(['run', '狀態', '檔數', '開始', '結束', '牆鐘（秒）'], [
        [b.get('run_id'), b.get('status'), b.get('tickers'), _local(b.get('started_at')), _local(b.get('ended_at')),
         round((datetime.fromisoformat(str(b['ended_at'])) - datetime.fromisoformat(str(b['started_at']))).total_seconds(), 3)
         if b.get('started_at') and b.get('ended_at') else None] for b in batches])

    out += ['', '**逐次嘗試**（旗標為抓取當下存的）', '']
    out += _table(['代號', '#', 'status', 'error', 'elapsed_ms', 'price', 'price_kind', 'quote_time（台北）',
                   'trading_date', 'session', 'delay', '旗標'], [
        [a.get('ticker'), a.get('attempt_number'), a.get('status'), a.get('error_code'), a.get('elapsed_ms'),
         a.get('price'), a.get('price_kind'), _local(a.get('quote_time')), a.get('trading_date'), a.get('session'),
         a.get('declared_delay_seconds'), _flags(a.get('quality_flags'))]
        for a in lines if a.get('kind') == 'attempt'])

    found = anomalies(lines)
    out += ['', f'**非成功的嘗試**：{len(found)} 筆', '']
    if found:
        out += _table(['代號', '#', 'status', 'error', 'reason', 'retry_after', 'elapsed_ms'], [
            [f['ticker'], f['attempt_number'], f['status'], f['error_code'], f['reason'],
             f['retry_after_seconds'], f['elapsed_ms']] for f in found])

    out += ['', f'**逐檔判定**（預期：三層旗標都有 `{CLOSED}`；台股 `trading_date` 為 {TW_DATE}、價格等於官方收盤；'
            f'美股 `trading_date` 為 {US_DATE}，價格比對為證據不足）', '']
    out += _table(['代號', '嘗試', '存入旗標', '估值旗標', '頁面旗標', 'trading_date', 'price', '官方收盤', '差', '價格比對', '不符之處'], [
        [r['ticker'], r['attempts'], r['layers']['stored'], r['layers']['valuation'], r['layers']['view'],
         r['trading_date'], r['price'], r.get('reference'), r.get('diff'), CHECK_TEXT[r['price_check']],
         '；'.join(r['problems']) or '無'] for r in results])
    matched = [r for r in results if not r['problems']]
    tw_equal = sum(r['price_check'] == 'equal' for r in results if r['market'] == 'TW')
    freshness = sum(1 for r in results if r['layers']['stored'] and 'freshness_unknown' in r['layers']['stored'])
    out += ['', f'- 符合全部預期：{len(matched)}／{len(results)} 檔。'
            f'不符的 {len(results) - len(matched)} 檔照實記錄，不重跑。',
            f'- 台股價格等於官方收盤：{tw_equal}／{len(TW_FIXED)} 檔。',
            f'- 美股 {len(FIXED) - len(TW_FIXED)} 檔的價格比對：證據不足（2026-09-25 使用者決定不另找來源）。',
            f'- 存入旗標帶 `freshness_unknown`：{freshness}／{len(results)} 檔。']
    return '\n'.join(out) + '\n'


def main(argv=None, out=sys.stdout):
    parser = argparse.ArgumentParser(prog='c76_report')
    parser.add_argument('--probe', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--execution')
    parser.add_argument('--digest')
    args = parser.parse_args(argv)
    closes = reference_closes(args.reference, TW_DATE)
    out.write(render(_jsonl(args.probe), closes, execution=args.execution, digest=args.digest))
    return 0


if __name__ == '__main__':
    sys.exit(main())

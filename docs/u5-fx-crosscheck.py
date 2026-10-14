"""U5 cross-check: Yahoo USD/TWD against the central bank's daily interbank close.

Read-only, no database. Run with the project's venv:
    .venv/Scripts/python.exe -I docs/u5-fx-crosscheck.py [days] [cbc.json]

Pass a saved copy of the central bank JSON on the company network: Python's strict
X.509 check rejects the TLS-inspection certificate there ("Missing Subject Key
Identifier"), while curl on Windows verifies against the system store. Download it with
    curl -sS -o cbc.json https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day
Verification is never turned off to get around this.

The central bank figure (cpx.cbc.gov.tw, data.gov.tw dataset 7232) is the Taipei
Foreign Exchange close at 16:00 Taipei. Yahoo's daily bar for TWD=X closes on its own
day boundary, not 16:00 Taipei, so the two are not the same instant: this checks that
Yahoo's level is plausible, not that it matches to the tick. The central bank value
never enters a valuation (U5 decision 7).
"""
from datetime import date
from decimal import Decimal
import json
import sys
import urllib.request

import yfinance as yf

CBC = 'https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day'


def central_bank(path=None):
    if path:
        with open(path, encoding='utf-8') as saved:
            rows = json.load(saved)
    else:
        with urllib.request.urlopen(CBC, timeout=30) as response:
            if 'application/json' not in response.headers.get('content-type', ''):
                raise SystemExit('central bank answered with something other than JSON')
            rows = json.load(response)
    return {date(int(r['日期'][:4]), int(r['日期'][4:6]), int(r['日期'][6:])): Decimal(r['NTD_USD']) for r in rows}


def yahoo(days):
    bars = yf.Ticker('TWD=X').history(period=f'{days * 2}d', interval='1d', auto_adjust=False)
    return {index.date(): Decimal(str(round(row['Close'], 4))) for index, row in bars.iterrows()}


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cbc, yh = central_bank(sys.argv[2] if len(sys.argv) > 2 else None), yahoo(days)
    shared = sorted(set(cbc) & set(yh))[-days:]
    print('date        cbc      yahoo    yahoo-cbc  pct')
    diffs = []
    for day in shared:
        diff = yh[day] - cbc[day]
        diffs.append(abs(diff / cbc[day] * 100))
        print(f'{day}  {cbc[day]:<8} {yh[day]:<8} {diff:+.4f}   {diff / cbc[day] * 100:+.3f}%')
    print(f'cbc latest {max(cbc)}; yahoo latest {max(yh)}; compared {len(shared)} days')
    if diffs:
        print(f'abs pct diff: max {max(diffs):.3f}%  mean {sum(diffs) / len(diffs):.3f}%')


if __name__ == '__main__':
    main()

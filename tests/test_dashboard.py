from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from stock_quote_fetcher.dashboard import calculate
from stock_quote_fetcher.models import Quote
from stock_quote_fetcher.web_input import preview_xlsx, template_xlsx, validate_rows, WebError
from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.otc_catalog import supplement, ENTRIES


def rows():
    return [{'ticker':'2330', 'quantity':'10', 'buy_price':'80'}, {'ticker':'AAPL', 'quantity':'2', 'buy_price':'8'}]


def test_verified_otc_resolution_and_valuation(monkeypatch):
    service = Dashboard.__new__(Dashboard)
    monkeypatch.setattr(service, 'catalog', lambda: ())
    holdings = validate_rows([{'ticker':'IFNNY', 'quantity':'8.554', 'buy_price':'40.88'}])
    resolved, names = service.resolve(holdings)
    instrument = resolved['IFNNY']
    assert instrument.exchange == 'OTCQX'
    assert instrument.provider_symbols['yahoo'] == 'IFNNY'
    from stock_quote_fetcher.providers import normalize
    stamp = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
    quote = normalize(instrument, 'yahoo', {
        'symbol':'IFNNY', 'quoteType':'EQUITY', 'currency':'USD',
        'exchangeTimezoneName':'America/New_York',
        'regularMarketPrice':'41', 'regularMarketTime':int(stamp.timestamp()),
        'exchangeDataDelayedBy':15,
    }, stamp)
    result = calculate(holdings, {'IFNNY':quote}, Decimal('30'), names)
    assert result['coverage'] == 1 and result['total'] == '10521.42'
    with pytest.raises(WebError, match='尚未儲存'):
        service.resolve(validate_rows([{'ticker':'UNKNOWNOTC', 'quantity':'1', 'buy_price':'1'}]))


def test_otc_supplement_does_not_duplicate_directory():
    assert supplement(ENTRIES) == ENTRIES


def prices():
    stamp = datetime(2026, 9, 8, 14, tzinfo=UTC)
    return {ticker: Quote(ticker, ticker, ticker, market, currency, 'yahoo', Decimal(price), 'last_trade', stamp, stamp, stamp.date(), 'regular', 'second')
            for ticker, market, currency, price in [('2330', 'TW', 'TWD', '100'), ('AAPL', 'US', 'USD', '10')]}


def modify_sheet(transform):
    source = ZipFile(BytesIO(template_xlsx()))
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            target.writestr(name, transform(data.decode()).encode() if name.endswith('sheet1.xml') else data)
    return output.getvalue()


def test_fixed_case():
    result = calculate(validate_rows(rows()), prices(), Decimal(30))
    assert (result['total'], result['cost'], result['profit'], result['return_pct']) == ('1600.00','1280.00','320.00','25.00')
    assert [r['weight'] for r in result['rows']] == ['62.50','37.50']


def test_missing_price_not_zero():
    q = prices()
    del q['AAPL']
    r = calculate(validate_rows(rows()), q, Decimal(30))
    assert r['total'] is None and r['profit'] is None
    assert r['known_total'] == '1000.00' and r['coverage'] == 1
    assert r['chart'][0]['weight'] == '100.00' and r['missing'] == ['AAPL']


def test_no_fx_and_market_filter():
    h = validate_rows(rows())
    r = calculate(h, prices(), None)
    assert r['total'] is None and r['chart'] == [] and r['needs_fx']
    assert len(r['summaries']) == 2
    assert calculate(h, prices(), None, market='TW')['total'] == '1000.00'


def test_all_missing_empty():
    assert calculate(validate_rows(rows()), {}, Decimal(30))['known_total'] is None
    assert calculate((), {}, None)['chart'] == []


def test_template_round_trip():
    p = preview_xlsx(template_xlsx())
    assert p['issues'] == [] and p['rows'][0]['ticker'] == '0050'
    assert p['sheets'] == ['持股']


@pytest.mark.parametrize('value,expected', [
    ('1068.0930000000001', '1068.093'),
    ('8.00185', '8.0019'), ('8.00184', '8.0018'),
    ('0.00005', '0.0001'), ('9.99995', '10'),
])
def test_import_rounds_four_places(value, expected):
    raw = modify_sheet(lambda s: s.replace(
        '<c r="C2" t="inlineStr"><is><t>50</t></is></c>',
        f'<c r="C2"><v>{value}</v></c>'))
    preview = preview_xlsx(raw)
    assert preview['issues'] == []
    assert preview['rows'][0]['buy_price'] == expected
    assert validate_rows(preview['rows'])[0].buy_price == Decimal(expected)


def test_manual_rounding_and_errors():
    data = rows()
    data[1]['quantity'] = '2.12345'
    assert validate_rows(data)[1].quantity == Decimal('2.1235')
    data[0]['quantity'] = '10.00001'
    with pytest.raises(WebError, match='請修正持股資料'):
        validate_rows(data)
    data = rows()
    data[0]['buy_price'] = '0.00004'
    with pytest.raises(WebError, match='四捨五入至 4 位小數後必須大於 0'):
        validate_rows(data)
    data[0]['buy_price'] = '9999999999999999.99999'
    with pytest.raises(WebError, match='四捨五入後數值最多 16 位整數'):
        validate_rows(data)


@pytest.mark.parametrize('bad', ['0','-1','NaN','Infinity','1,000','$12','1e999999','1e-10000'])
def test_invalid_numbers(bad):
    r = rows()
    r[0]['quantity'] = bad
    with pytest.raises(WebError):
        validate_rows(r)


def test_duplicate_fractional_taiwan():
    with pytest.raises(WebError):
        validate_rows(rows() + [rows()[0]])
    r = rows(); r[0]['quantity'] = '1.5'
    with pytest.raises(WebError):
        validate_rows(r)


@pytest.mark.parametrize('cell', ['<c r="A2"><v>50</v></c>', '<c r="A2" t="str"><f>"0050"</f><v>0050</v></c>', '<c r="A2" t="b"><v>1</v></c>', '<c r="A2" t="e"><v>#VALUE!</v></c>'])
def test_reject_unsafe_ticker_cell(cell):
    raw = modify_sheet(lambda s: s.replace('<c r="A2" t="inlineStr"><is><t>0050</t></is></c>', cell))
    p = preview_xlsx(raw)
    assert p['issues'][0]['row'] == 2 and p['issues'][0]['field'] == 'ticker'


def test_blank_middle_and_tail():
    raw = modify_sheet(lambda s: s.replace('<row r="3">', '<row r="4">').replace('r="A3"','r="A4"').replace('r="B3"','r="B4"').replace('r="C3"','r="C4"'))
    assert preview_xlsx(raw)['issues'][0]['row'] == 3
    raw = modify_sheet(lambda s: s.replace('</sheetData>', '<row r="9999"></row></sheetData>'))
    assert preview_xlsx(raw)['issues'] == []


def test_unknown_sheet_and_oversize():
    with pytest.raises(WebError): preview_xlsx(template_xlsx(), '不存在')
    with pytest.raises(WebError): preview_xlsx(b'x' * (5*1024*1024+1))


@pytest.mark.parametrize('market,limit', [('ALL', 15), ('TW', 10), ('US', 10)])
@pytest.mark.parametrize('extra', [0, 1, 3])
def test_other_group_exact(market, limit, extra):
    from dataclasses import replace
    base = prices()['2330' if market == 'TW' else 'AAPL']
    count = limit + extra
    tickers = [str(1000+i) if market == 'TW' else f'A{i}' for i in range(count)]
    data = [{'ticker':ticker, 'quantity':'1', 'buy_price':'1'} for ticker in tickers]
    q = {ticker:replace(base, ticker=ticker, price=Decimal(i+1)) for i,ticker in enumerate(tickers)}
    result = calculate(validate_rows(data), q, Decimal(30), market=market)
    chart = result['chart']
    assert len(chart) == limit + bool(extra)
    assert [r['ticker'] for r in chart[:limit]] == list(reversed(tickers))[:limit]
    assert sum(Decimal(r['value']) for r in chart) == Decimal(result['known_total'])
    if extra:
        factor = 1 if market == 'TW' else 30
        other = Decimal(extra*(extra+1)//2*factor)
        assert Decimal(chart[-1]['value']) == other
        assert chart[-1]['members'] == list(reversed(tickers[:extra]))
        assert Decimal(chart[-1]['weight']) == (other / Decimal(result['known_total']) * 100).quantize(Decimal('.01'))
    else:
        assert all('members' not in r for r in chart)


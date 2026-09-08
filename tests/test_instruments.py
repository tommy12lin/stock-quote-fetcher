import json

import pytest

from stock_quote_fetcher.input import parse_holdings
from stock_quote_fetcher.instruments import (
    CatalogError, CatalogInstrument, parse_nasdaq_listed, parse_nasdaq_other,
    parse_tpex_isin, parse_twse_companies, parse_twse_funds, resolve_holdings,
)


def encoded(rows):
    return json.dumps(rows,ensure_ascii=False).encode()


def test_twse_companies_and_funds():
    companies = parse_twse_companies(encoded([
        {'公司代號':'2330','公司簡稱':'台積電'},
        {'公司代號':'1101','公司簡稱':'台泥'},
    ]))
    assert [(x.ticker,x.asset_type,x.provider_symbols['yahoo']) for x in companies] == [
        ('2330','stock','2330.TW'),('1101','stock','1101.TW')]
    funds = parse_twse_funds(encoded([
        {'基金代號':'0050','基金簡稱':'元大台灣50','基金類型':'國內成分證券指數股票型基金'},
        {'基金代號':'00400A','基金簡稱':'主動ETF','基金類型':'國內成分證券主動式交易所交易基金(股票)'},
        {'基金代號':'00687C','基金簡稱':'外幣ETF','基金類型':'國外成份/加掛外幣證券指數股票型基金'},
    ]))
    assert [x.ticker for x in funds] == ['0050','00400A']


def tpex_html():
    rows = [
        ['有價證券代號及名稱','ISIN','上市日','市場別','產業別','CFICode','備註'],
        ['上櫃認購(售)權證'],['700019　權證','TWX','2025/1/1','上櫃','','RWSCCA',''],
        ['ETF'],['00411A　主動統一前沿科技','TW1','2026/8/26','上櫃','','CEOIEU',''],
        ['00687C　國泰20年美債+櫃U','TW2','2017/1/1','上櫃','','CEOIBU',''],
        ['ETN'],['020000　ETN','TW3','2020/1/1','上櫃','','DTXXXX',''],
        ['股票'],['6488　環球晶','TW4','2015/9/25','上櫃','半導體業','ESVUFR',''],
        ['特別股'],['6541A　特別股','TW5','2020/1/1','上櫃','','EPXXXX',''],
    ]
    html = '<table>' + ''.join('<tr>'+''.join(f'<td>{cell}</td>' for cell in row)+'</tr>' for row in rows) + '</table>'
    return html.encode('cp950')


def test_tpex_uses_official_sections_and_cfi_and_excludes_foreign_currency():
    entries = parse_tpex_isin(tpex_html())
    assert [(x.ticker,x.asset_type,x.provider_symbols['yahoo']) for x in entries] == [
        ('00411A','etf','00411A.TWO'),('6488','stock','6488.TWO')]


def test_tpex_category_cfi_conflict_fails_whole_source():
    payload = tpex_html().decode('cp950').replace('CEOIEU','RWSCCA').encode('cp950')
    with pytest.raises(CatalogError,match='CFICode'):
        parse_tpex_isin(payload)


NASDAQ = '''Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N
VOO|Vanguard ETF|G|N|N|100|Y|N
BADW|Issuer - Warrant|S|N|N|100|N|N
TEST|Test Common Stock|S|Y|N|100|N|N
LATE|Late Common Stock|S|N|D|100|N|N
File Creation Time: 0908202612|||||||
'''.encode()

OTHER = '''ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.B|Berkshire Hathaway Inc. Class B Common Stock|N|BRK.B|N|100|N|BRK=B
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
ABR$D|Arbor Preferred Stock|N|ABRpD|N|100|N|ABR-D
UNIT.U|Example Units|N|UNIT.U|N|100|N|UNIT=
OTC|Example Common Stock|X|OTC|N|100|N|OTC
File Creation Time: 0908202612|||||||
'''.encode()


def test_nasdaq_filters_unsupported_and_maps_share_class():
    listed = parse_nasdaq_listed(NASDAQ)
    assert [(x.ticker,x.asset_type) for x in listed] == [('AAPL','stock'),('VOO','etf')]
    other = parse_nasdaq_other(OTHER)
    assert [(x.ticker,x.asset_type,x.provider_symbols['yahoo']) for x in other] == [
        ('BRK.B','stock','BRK-B'),('SPY','etf','SPY')]
    assert {'BRK.B','BRK=B','BRK-B'} <= set(other[0].aliases)


@pytest.mark.parametrize('parser,payload',[
    (parse_twse_companies,b'not json'),(parse_twse_companies,b'[]'),
    (parse_twse_funds,encoded([{'基金代號':'0050','基金簡稱':'x','基金類型':'共同基金'}])),
    (parse_tpex_isin,b'not a catalog'),(parse_nasdaq_listed,b'wrong|header\na|b\n'),
])
def test_invalid_or_changed_sources_fail(parser,payload):
    with pytest.raises(CatalogError):
        parser(payload)


def test_resolve_known_unknown_leading_zero_and_alias():
    entries = (*parse_twse_companies(encoded([{'公司代號':'2330','公司簡稱':'台積電'}])),
               *parse_twse_funds(encoded([{'基金代號':'0050','基金簡稱':'元大台灣50','基金類型':'國內成分證券指數股票型基金'}])),
               *parse_nasdaq_other(OTHER))
    holdings = parse_holdings('ticker,buy_price,quantity\n0050,1,1\n2330,1,1\nBRK-B,1,0.5\nUNKNOWN,1,1\n')
    resolved, issues = resolve_holdings(holdings,entries)
    assert resolved['0050'].provider_symbols['yahoo'] == '0050.TW'
    assert resolved['2330'].provider_symbols['yahoo'] == '2330.TW'
    assert resolved['BRK-B'].ticker == 'BRK-B'
    assert resolved['BRK-B'].instrument_id.endswith(':BRK.B')
    assert issues == (type(issues[0])('UNKNOWN','not_found_or_unsupported'),)


def test_resolve_reports_ambiguous_alias_without_guessing():
    first = CatalogInstrument('one','ABC','US','USD','NYSE','stock','One',{'yahoo':'ABC'},('DUP',))
    second = CatalogInstrument('two','XYZ','US','USD','NASDAQ','stock','Two',{'yahoo':'XYZ'},('DUP',))
    holdings = parse_holdings('ticker,buy_price,quantity\nDUP,1,1\n')
    resolved, issues = resolve_holdings(holdings,(first,second))
    assert not resolved and issues[0].reason == 'ambiguous_mapping'


def test_catalog_models_are_immutable():
    entry = CatalogInstrument('id','AAPL','US','USD','NASDAQ','stock','Apple',{'yahoo':'AAPL'})
    with pytest.raises(TypeError):
        entry.provider_symbols['yahoo'] = 'changed'


def test_stock_keyword_matching_uses_word_boundaries():
    payload = NASDAQ.replace(b'AAPL|Apple Inc. - Common Stock',b'BRLT|BrightSpring Health Services, Inc. - Common Stock')
    entries = parse_nasdaq_listed(payload)
    assert 'BRLT' in {entry.ticker for entry in entries}

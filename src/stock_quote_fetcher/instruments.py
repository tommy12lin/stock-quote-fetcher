"""Official instrument-list parsing and deterministic provider symbol mapping."""

from dataclasses import dataclass
from html.parser import HTMLParser
import csv
import io
import json
import re
from types import MappingProxyType
from typing import Iterable, Mapping

from stock_quote_fetcher.models import Holding, Instrument, Market


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogInstrument:
    instrument_id: str
    ticker: str
    market: Market
    currency: str
    exchange: str
    asset_type: str
    name: str
    provider_symbols: Mapping[str, str]
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'market', Market(self.market))
        object.__setattr__(self, 'provider_symbols', MappingProxyType(dict(self.provider_symbols)))
        if self.asset_type not in {'stock', 'etf'} or self.currency not in {'TWD', 'USD'}:
            raise CatalogError('Unsupported catalog asset type or currency.')
        if not self.ticker or not self.name or not self.exchange or not self.instrument_id:
            raise CatalogError('Catalog instrument fields cannot be empty.')
        normalized = tuple(dict.fromkeys(alias.upper() for alias in (self.ticker, *self.aliases)))
        object.__setattr__(self, 'aliases', normalized)

    def to_instrument(self, input_ticker: str | None = None) -> Instrument:
        return Instrument(self.instrument_id, input_ticker or self.ticker, self.market, self.currency,
                          self.provider_symbols, self.exchange, self.asset_type)


def _json_rows(payload: bytes) -> list[dict]:
    try:
        rows = json.loads(payload.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CatalogError('Official catalog is not valid UTF-8 JSON.') from None
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise CatalogError('Official catalog JSON must be a nonempty array of objects.')
    return rows


def _required(row: dict, *keys: str) -> tuple[str, ...]:
    values = tuple(row.get(key) for key in keys)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise CatalogError(f'Official catalog row lacks required fields: {", ".join(keys)}.')
    return tuple(value.strip() for value in values)


def parse_twse_companies(payload: bytes) -> tuple[CatalogInstrument, ...]:
    result = []
    for row in _json_rows(payload):
        ticker, name = _required(row, '公司代號', '公司簡稱')
        result.append(_tw(ticker, name, 'TWSE', 'stock'))
    return _unique(result)


def parse_twse_funds(payload: bytes) -> tuple[CatalogInstrument, ...]:
    result = []
    for row in _json_rows(payload):
        ticker, name, fund_type = _required(row, '基金代號', '基金簡稱', '基金類型')
        if not ('指數股票型基金' in fund_type or '交易所交易基金' in fund_type):
            continue
        if _foreign_currency_etf(ticker, 'TWSE'):
            continue
        result.append(_tw(ticker, name, 'TWSE', 'etf'))
    if not result:
        raise CatalogError('TWSE fund catalog contains no ETF rows.')
    return _unique(result)


def _tw(ticker: str, name: str, exchange: str, asset_type: str) -> CatalogInstrument:
    if not re.fullmatch(r'[0-9][0-9A-Z]*', ticker):
        raise CatalogError('Taiwan official catalog contains an invalid ticker.')
    suffix = '.TW' if exchange == 'TWSE' else '.TWO'
    return CatalogInstrument(f'tw:{exchange.lower()}:{ticker}', ticker, Market.TW, 'TWD',
                             exchange, asset_type, name, {'yahoo': ticker + suffix})


def _foreign_currency_etf(ticker: str, exchange: str) -> bool:
    # Official exchange coding rules identify foreign-currency ETF classes.
    return len(ticker) == 6 and ticker[-1] in ({'K','C','M','S','V'} if exchange == 'TWSE' else {'K','C'})


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'tr':
            self.current_row = []
        elif tag.lower() == 'td' and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'td' and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(''.join(self.current_cell).strip())
            self.current_cell = None
        elif tag.lower() == 'tr' and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None


def parse_tpex_isin(payload: bytes) -> tuple[CatalogInstrument, ...]:
    try:
        text = payload.decode('cp950')
    except UnicodeDecodeError:
        raise CatalogError('TPEx ISIN catalog is not valid CP950 HTML.') from None
    parser = _TableParser()
    parser.feed(text)
    section = None
    result = []
    for cells in parser.rows:
        if len(cells) == 1:
            section = cells[0]
            continue
        if section not in {'股票', 'ETF'} or len(cells) < 7:
            continue
        first = cells[0].replace('\u3000', ' ').strip()
        parts = first.split(maxsplit=1)
        if len(parts) != 2:
            raise CatalogError('TPEx ISIN row lacks ticker or name.')
        ticker, name = parts
        if cells[3] != '上櫃':
            raise CatalogError('TPEx ISIN row has an unexpected market.')
        # The section is the official security type; CFICode remains validated evidence.
        cfi = cells[5]
        expected_prefix = 'ES' if section == '股票' else 'CE'
        if not cfi.startswith(expected_prefix):
            raise CatalogError('TPEx ISIN security category conflicts with CFICode.')
        if section == 'ETF' and _foreign_currency_etf(ticker, 'TPEx'):
            continue
        result.append(_tw(ticker, name, 'TPEx', 'stock' if section == '股票' else 'etf'))
    if not result:
        raise CatalogError('TPEx ISIN catalog contains no supported stock or ETF rows.')
    return _unique(result)


_STOCK_PATTERNS = (
    r'\bCOMMON STOCK\b', r'\bCOMMON SHARES?\b', r'\bORDINARY SHARES?\b',
    r'\bAMERICAN DEPOSITA(?:RY|ORY) SHARES?\b', r'\bADS\b', r'\bADR\b',
    r'\bNEW YORK REGISTRY SHARES?\b',
)
_EXCLUDED_PATTERNS = (
    r'\bWARRANTS?\b', r'\bRIGHTS?\b', r'\bUNITS?\b', r'\bPREFERRED\b',
    r'\bPREFERENCE\b', r'\bNOTES?\b', r'\bBONDS?\b', r'\bDEBENTURES?\b',
    r'\bCERTIFICATES?\b',
)


def _us_asset_type(name: str, etf: str) -> str | None:
    upper = name.upper()
    if etf == 'Y':
        return 'etf'
    if etf != 'N' or any(re.search(pattern, upper) for pattern in _EXCLUDED_PATTERNS):
        return None
    return 'stock' if any(re.search(pattern, upper) for pattern in _STOCK_PATTERNS) else None


def _pipe_rows(payload: bytes) -> list[dict[str, str]]:
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise CatalogError('Nasdaq symbol directory is not UTF-8 text.') from None
    reader = csv.DictReader(io.StringIO(text), delimiter='|')
    if not reader.fieldnames:
        raise CatalogError('Nasdaq symbol directory lacks a header.')
    return [row for row in reader if row and not next(iter(row.values()), '').startswith('File Creation Time')]


def parse_nasdaq_listed(payload: bytes) -> tuple[CatalogInstrument, ...]:
    result = []
    for row in _pipe_rows(payload):
        if set(('Symbol','Security Name','Market Category','Test Issue','Financial Status','ETF')) - row.keys():
            raise CatalogError('Nasdaq-listed directory schema changed.')
        ticker, name, category = _required(row, 'Symbol','Security Name','Market Category')
        if row['Test Issue'] != 'N' or row['Financial Status'] != 'N':
            continue
        asset_type = _us_asset_type(name, row['ETF'])
        if asset_type:
            result.append(_us(ticker, name, 'NASDAQ-' + category, asset_type, ticker, (ticker,)))
    if not result:
        raise CatalogError('Nasdaq-listed directory contains no supported securities.')
    return _unique(result)


def parse_nasdaq_other(payload: bytes) -> tuple[CatalogInstrument, ...]:
    exchanges = {'A':'NYSE American','N':'NYSE','P':'NYSE Arca','Z':'Cboe BZX','V':'IEX'}
    result = []
    for row in _pipe_rows(payload):
        required = ('ACT Symbol','Security Name','Exchange','CQS Symbol','ETF','Test Issue','NASDAQ Symbol')
        if set(required) - row.keys():
            raise CatalogError('Other-listed directory schema changed.')
        act, name, exchange = _required(row, 'ACT Symbol','Security Name','Exchange')
        if row['Test Issue'] != 'N' or exchange not in exchanges:
            continue
        asset_type = _us_asset_type(name, row['ETF'])
        if not asset_type:
            continue
        # Yahoo represents class separators with a hyphen (for example BRK.B -> BRK-B).
        yahoo = act.replace('.', '-').replace('$', '-P')
        aliases = tuple(value for value in (act, row['CQS Symbol'].strip(), row['NASDAQ Symbol'].strip(), yahoo) if value)
        result.append(_us(act, name, exchanges[exchange], asset_type, yahoo, aliases))
    if not result:
        raise CatalogError('Other-listed directory contains no supported securities.')
    return _unique(result)


def _us(ticker, name, exchange, asset_type, yahoo, aliases):
    if not re.fullmatch(r'[A-Z][A-Z0-9.$=+\-]*', ticker):
        raise CatalogError('US official catalog contains an invalid ticker.')
    return CatalogInstrument(f'us:{exchange.lower().replace(" ","-")}:{ticker}', ticker,
                             Market.US, 'USD', exchange, asset_type, name,
                             {'yahoo': yahoo}, aliases)


def _unique(entries: Iterable[CatalogInstrument]) -> tuple[CatalogInstrument, ...]:
    result = tuple(entries)
    if len({entry.ticker for entry in result}) != len(result):
        raise CatalogError('Official source contains duplicate supported tickers.')
    return result


@dataclass(frozen=True)
class ResolutionIssue:
    ticker: str
    reason: str


def resolve_holdings(holdings: Iterable[Holding], entries: Iterable[CatalogInstrument]):
    index: dict[tuple[Market, str], list[CatalogInstrument]] = {}
    for entry in entries:
        for alias in entry.aliases:
            index.setdefault((entry.market, alias), []).append(entry)
    resolved, issues = {}, []
    for holding in holdings:
        matches = {entry.instrument_id: entry for entry in index.get((holding.market, holding.ticker), ())}
        if not matches:
            issues.append(ResolutionIssue(holding.ticker, 'not_found_or_unsupported'))
        elif len(matches) > 1:
            issues.append(ResolutionIssue(holding.ticker, 'ambiguous_mapping'))
        else:
            entry = next(iter(matches.values()))
            if entry.currency != holding.currency:
                issues.append(ResolutionIssue(holding.ticker, 'currency_mismatch'))
            else:
                resolved[holding.ticker] = entry.to_instrument(holding.ticker)
    return resolved, tuple(issues)

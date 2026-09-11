"""Adapters and pure normalizers; subprocess boundary enforces an operation deadline."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import json
import subprocess
import sys

from stock_quote_fetcher.models import FetchResult, FetchStatus, Market, Quote, Session, TimePrecision
from stock_quote_fetcher.quality import assess, bounds, timezone

PARSER_VERSION = 'quote-v1'


@dataclass(frozen=True)
class Operation:
    result: FetchResult
    evidence: dict
    retry_after: float | None = None


def failure(instrument, provider, status, reason, **evidence):
    return Operation(FetchResult(instrument.instrument_id,provider,status,error=reason),
                     {'parser_version':PARSER_VERSION,'reason':reason,**evidence})


def symbol_for(instrument, provider):
    if provider == 'yahoo':
        return instrument.provider_symbols['yahoo']
    if provider == 'finnhub':
        # Official canonical ticker is the final component of the stable catalog id.
        return instrument.instrument_id.rsplit(':',1)[-1]
    return instrument.provider_symbols['yahoo'].split('.')[0]


def applicable(instrument, provider):
    return (provider == 'yahoo' or (provider == 'finnhub' and instrument.market == Market.US)
            or (provider == 'twse' and instrument.exchange == 'TWSE')
            or (provider == 'tpex' and instrument.exchange == 'TPEx'))


def positive(value):
    if isinstance(value,bool) or value is None:
        raise ValueError('price')
    result = Decimal(str(value).replace(',',''))
    if not result.is_finite() or result <= 0:
        raise ValueError('price')
    return result


def timestamp(value):
    if value in (None,0,'0'):
        return None
    if isinstance(value,bool):
        raise ValueError('timestamp')
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError('timestamp')
    return datetime.fromtimestamp(int(number),UTC)


def normalize(instrument, provider, payload, received_at):
    symbol = symbol_for(instrument,provider)
    kind, precision, session, delay = 'last_trade', TimePrecision.SECOND, Session.REGULAR, None
    currency = instrument.currency
    if provider == 'yahoo':
        if payload.get('symbol') != symbol:
            raise ValueError('symbol_mismatch')
        expected_type = 'ETF' if instrument.asset_type == 'etf' else 'EQUITY'
        if payload.get('quoteType') != expected_type:
            raise ValueError('asset_type_mismatch')
        if payload.get('exchangeTimezoneName') != str(timezone(instrument.market)):
            raise ValueError('timezone_mismatch')
        currency = payload.get('currency')
        if not isinstance(currency,str):
            raise ValueError('currency_missing')
        price, stamp = positive(payload.get('regularMarketPrice')), timestamp(payload.get('regularMarketTime'))
        raw_delay = payload.get('exchangeDataDelayedBy')
        if raw_delay is not None:
            number = Decimal(str(raw_delay))
            if not number.is_finite() or number < 0 or number != number.to_integral_value():
                raise ValueError('delay')
            delay = int(number)*60
    elif provider == 'finnhub':
        price, stamp = positive(payload.get('c')), timestamp(payload.get('t'))
        # Quote API has no currency or session fields. Currency comes from official
        # US catalog; the timestamp must lie inside a regular calendar session.
        if stamp:
            day_bounds = bounds(instrument.market,stamp.astimezone(timezone(instrument.market)).date())
            if day_bounds is None or not day_bounds[0] <= stamp <= day_bounds[1]:
                session = Session.UNKNOWN
    else:
        code, field = ('Code','ClosingPrice') if provider == 'twse' else ('SecuritiesCompanyCode','Close')
        if payload.get(code) != symbol:
            raise ValueError('symbol_mismatch')
        price = positive(payload.get(field))
        raw_date = str(payload.get('Date','')).replace('/','').replace('-','')
        if len(raw_date) == 7 and raw_date.isdigit():
            day = date(int(raw_date[:3])+1911,int(raw_date[3:5]),int(raw_date[5:]))
        elif len(raw_date) == 8 and raw_date.isdigit():
            day = date(int(raw_date[:4]),int(raw_date[4:6]),int(raw_date[6:]))
        else:
            raise ValueError('date')
        official_bounds = bounds(instrument.market,day)
        if official_bounds is None:
            raise ValueError('non_trading_date')
        if received_at < official_bounds[1]:
            raise ValueError('close_not_yet_available')
        # Official close has a trading date, not a timestamp of last transaction.
        quote = Quote(instrument.instrument_id,instrument.ticker,symbol,instrument.market,currency,provider,
                      price,'close',None,received_at,day,Session.CLOSED,TimePrecision.DAY,
                      asset_type=instrument.asset_type)
        return assess(quote)
    quote = Quote(instrument.instrument_id,instrument.ticker,symbol,instrument.market,currency,provider,
                  price,kind,stamp,received_at,None,session,precision,delay,
                  asset_type=instrument.asset_type)
    return assess(quote)


def fetch_one(instrument, provider, config, timeout):
    request = {'provider':provider,'symbol':symbol_for(instrument,provider),'timeout':timeout,
               'company_ca_file':config.company_ca_file if provider in config.relaxed_providers else '',
               'relaxed':provider in config.relaxed_providers}
    try:
        process = subprocess.run([sys.executable,'-m','stock_quote_fetcher.provider_worker'],
                                 input=json.dumps(request),capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return failure(instrument,provider,'timeout','operation_deadline')
    if process.returncode != 0:
        return failure(instrument,provider,'provider_error','worker_failed')
    payload = None
    try:
        response = json.loads(process.stdout)
        received = datetime.fromisoformat(response['received_at'])
        if response['status'] != 'success':
            op = failure(instrument,provider,response['status'],response['reason'])
            return Operation(op.result,op.evidence,response.get('retry_after'))
        payload = response['payload']
        quote = normalize(instrument,provider,payload,received)
        quote = assess(quote,poll_seconds=config.poll_interval_seconds)
        return Operation(FetchResult(instrument.instrument_id,provider,FetchStatus.SUCCESS,quote),
                         {'parser_version':PARSER_VERSION,'fields':payload,
                          'currency_basis':'official_catalog' if provider == 'finnhub' else 'response',
                          'tls_relaxed':request['relaxed']})
    except (ValueError,TypeError,KeyError,OverflowError,ArithmeticError):
        return failure(instrument,provider,'invalid_payload','normalization_failed',
                       fields=payload if isinstance(payload,dict) else None)

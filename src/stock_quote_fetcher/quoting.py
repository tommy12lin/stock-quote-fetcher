"""Single quote orchestration: commit evidence before publishing valuation exports."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import csv
import json
import random
import time
from uuid import uuid4

from stock_quote_fetcher.config import load_database_config, load_quote_config, load_instrument_catalog_config, runtime_image_id
from stock_quote_fetcher.input import parse_holdings
from stock_quote_fetcher.instruments import resolve_holdings
from stock_quote_fetcher.models import Instrument, QualityFlag as F
from stock_quote_fetcher.providers import applicable, failure, fetch_one, symbol_for
from stock_quote_fetcher.quality import assess, bounds
from stock_quote_fetcher.storage import Storage
from stock_quote_fetcher.valuation import value_holdings


class CollectionInterrupted(RuntimeError):
    """A cooperative stop request observed between bounded provider operations."""


class QuoteRunner:
    def __init__(self, storage, config, *, fetch=None, monotonic=time.monotonic, sleep=time.sleep,
                 stop_requested=lambda: False):
        self.storage, self.config, self.fetch = storage, config, fetch or fetch_one
        self.monotonic, self.sleep = monotonic, sleep
        self.stop_requested = stop_requested
        self.cooldown = {}
        self.next_operation = {}
        self.events = []

    def restore_cooldowns(self, remaining_seconds):
        point = self.monotonic()
        for provider, remaining in remaining_seconds.items():
            if remaining > 0:
                self.cooldown[provider] = point + remaining

    def collect(self, cycle, instrument, provider, deadline):
        for number in range(1,self.config.max_retries+2):
            attempt, quote_id = uuid4(), uuid4()
            self.storage.start_attempt(attempt,cycle,provider=provider,instrument_id=instrument.instrument_id,
                                       ticker=instrument.ticker,attempt_number=number)
            start = self.monotonic()
            remaining = deadline - start
            until = self.cooldown.get(provider,0)
            executed = False
            if self.stop_requested():
                op = failure(instrument,provider,'interrupted','shutdown_requested')
            elif remaining <= 0:
                op = failure(instrument,provider,'timeout','cycle_budget_exhausted')
            elif until > start:
                op = failure(instrument,provider,'rate_limited','source_cooldown')
            else:
                spacing = max(0,self.next_operation.get(provider,0)-self.monotonic())
                if spacing:
                    self.sleep(min(spacing,remaining))
                remaining = deadline-self.monotonic()
                if remaining <= 0:
                    op = failure(instrument,provider,'timeout','cycle_budget_exhausted')
                else:
                    executed = True
                    self.next_operation[provider] = self.monotonic()+1
                    op = self.fetch(instrument,provider,self.config,min(remaining,self.config.operation_timeout_seconds))
            elapsed = max(0,int((self.monotonic()-start)*1000))
            result = op.result
            wait = op.retry_after
            if result.status.value == 'rate_limited' and wait is None:
                wait = max(1, until-self.monotonic()) if not executed and until > self.monotonic() else 60
            evidence = {**op.evidence,'executed':executed,'retry_after_seconds':op.retry_after,
                        'effective_cooldown_seconds':wait}
            saved = self.storage.finish_attempt(attempt,result,elapsed_ms=elapsed,
                                                quote_id=quote_id,provider_evidence=evidence)
            self.events.append({'attempt_id':str(attempt),'provider':provider,'ticker':instrument.ticker,
                                'attempt_number':number,'status':result.status.value,'reason':result.error,
                                'executed':executed,'elapsed_ms':elapsed,'retry_after_seconds':op.retry_after})
            if result.quote is not None:
                return saved,result.quote
            if not executed:
                break
            if wait is not None:
                self.cooldown[provider] = self.monotonic()+wait
            if result.status.value not in {'timeout','network_error','rate_limited'} or number > self.config.max_retries:
                break
            delay = max(wait or 0,2**(number-1)+random.uniform(0,0.25))
            if self.monotonic()+delay >= deadline:
                break
            self.sleep(delay)
        return None,None

    def choose_cache(self, instrument):
        for identity, quote in self.storage.cached_quotes(instrument,self.config.valuation):
            if (quote.provider_symbol != symbol_for(instrument,self.config.valuation)
                    or quote.quote_time is None or quote.received_at > datetime.now(UTC)):
                continue
            checked = assess(quote,as_of=datetime.now(UTC),poll_seconds=self.config.poll_interval_seconds)
            holding = next(h for h in self.holdings if h.ticker == instrument.ticker)
            row = value_holdings([holding],{holding.ticker:checked}).rows[0]
            if row.market_value is None or {F.SESSION_UNKNOWN,F.TIME_UNKNOWN,F.FRESHNESS_UNKNOWN} & row.quality_flags:
                continue
            checked = replace(checked,quality_flags=checked.quality_flags | {F.CACHED,F.STALE})
            return identity,checked
        return None,None

    def run_cycle(self, run_id, holdings, resolved, issues, *, market, scheduled_at,
                  scheduled_cycle_id=None, budget=None):
        self.holdings = holdings
        cycle = uuid4()
        event_start = len(self.events)
        self.storage.start_cycle(cycle,run_id,market=market.value,scheduled_at=scheduled_at,
                                 scheduled_cycle_id=scheduled_cycle_id)
        selected, flags, fetched, comparisons = {}, {}, {}, []
        # budget, when given, is what this cycle may take out of a total its caller is
        # holding to; the configured per-cycle limit still applies on top of it.
        seconds = self.config.cycle_budget_seconds if budget is None else min(self.config.cycle_budget_seconds, budget)
        deadline = self.monotonic()+seconds
        group = [h for h in holdings if h.market == market]
        try:
            # Complete valuation source first; comparison requests cannot consume its budget.
            for provider in (self.config.valuation,*self.config.comparison):
                for holding in group:
                    if self.stop_requested():
                        raise CollectionInterrupted('shutdown requested')
                    instrument = resolved.get(holding.ticker)
                    if instrument is None:
                        if provider != self.config.valuation:
                            continue
                        instrument = Instrument(f'unresolved:{market}:{holding.ticker}',holding.ticker,market,holding.currency)
                        attempt = uuid4()
                        self.storage.start_attempt(attempt,cycle,provider=provider,instrument_id=instrument.instrument_id,
                                                   ticker=holding.ticker,attempt_number=1)
                        reason = next(i.reason for i in issues if i.ticker == holding.ticker)
                        op = failure(instrument,provider,'unsupported_symbol',reason)
                        self.storage.finish_attempt(attempt,op.result,elapsed_ms=0,provider_evidence={**op.evidence,'executed':False})
                        self.events.append({'provider':provider,'ticker':holding.ticker,'status':'unsupported_symbol',
                                            'reason':reason,'executed':False,'attempt_id':str(attempt)})
                        continue
                    if not applicable(instrument,provider):
                        continue
                    identity, quote = self.collect(cycle,instrument,provider,deadline)
                    if self.stop_requested():
                        raise CollectionInterrupted('shutdown requested')
                    if quote:
                        fetched[(holding.ticker,provider)] = quote
                    if provider == self.config.valuation:
                        if quote is None:
                            identity,quote = self.choose_cache(instrument)
                        if quote is not None:
                            selected[holding.ticker] = identity
                            flags[holding.ticker] = quote.quality_flags
            report = self.storage.finish_cycle(cycle,selected_quotes=selected,quality_flags=flags)
            for holding in group:
                main = fetched.get((holding.ticker,self.config.valuation))
                instrument = resolved.get(holding.ticker)
                for provider in self.config.comparison:
                    if instrument and applicable(instrument,provider):
                        comparisons.append(compare(main,fetched.get((holding.ticker,provider)),holding.ticker,provider))
            return cycle, report, comparisons, self.events[event_start:]
        except BaseException:
            if not self.storage.failed:
                self.storage.stop_cycle(cycle,status='interrupted',reason='quote_interrupted')
            raise

    def run(self, run_id, holdings, resolved, issues, *, budget=None):
        """budget: seconds for this whole call, shared by every market in it.

        Without it each market cycle gets its own full cycle_budget_seconds, which is
        right for the monitor — it schedules one cycle per market — but wrong for a caller
        working to a single deadline: a batch holding both TW and US positions would take
        two budgets and overrun that deadline by a whole one. Measured while choosing
        D3's refresh deadline; see docs/cloud-C7-evidence.md.
        """
        reports, comparisons = [], []
        # One independent budget for each market cycle, shared by all its sources.
        started = self.monotonic()
        for market in sorted({h.market for h in holdings}):
            share = None if budget is None else max(0, budget - (self.monotonic() - started))
            cycle, report, compared, _ = self.run_cycle(
                run_id, holdings, resolved, issues, market=market, scheduled_at=datetime.now(UTC),
                budget=share)
            reports.append((cycle,report))
            comparisons.extend(compared)
        self.storage.finish_run(run_id)
        return reports, comparisons


def compare(main, other, ticker, provider):
    result = {'ticker':ticker,'valuation_provider':'yahoo','comparison_provider':provider,
              'aligned':False,'reason':'missing_quote'}
    if main is None or other is None:
        return result
    result.update(valuation_price=str(main.price),comparison_price=str(other.price),
                  valuation_time=main.quote_time.isoformat() if main.quote_time else None,
                  comparison_time=other.quote_time.isoformat() if other.quote_time else None,
                  valuation_trading_date=str(main.trading_date),comparison_trading_date=str(other.trading_date))
    invalid = {F.FUTURE_TIME,F.CURRENCY_MISMATCH,F.SESSION_UNKNOWN,F.PRICE_KIND_MISMATCH}
    if main.currency != other.currency or invalid & (main.quality_flags | other.quality_flags):
        result['reason'] = 'quality_not_comparable'
        return result
    aligned = False
    if provider == 'finnhub':
        aligned = (main.quote_time is not None and main.quote_time == other.quote_time
                   and main.price_kind == other.price_kind and main.trading_date == other.trading_date)
    elif main.trading_date == other.trading_date and main.quote_time:
        session_bounds = bounds(main.market,main.trading_date)
        # A last-trade field only proves the close when stamped at the closing boundary.
        aligned = bool(session_bounds and abs((main.quote_time-session_bounds[1]).total_seconds()) <= 5)
    if aligned:
        from stock_quote_fetcher.valuation import exact_sum
        result.update(aligned=True,reason='same_time_and_basis',difference=str(exact_sum([main.price,other.price.copy_negate()])),
                      equal=main.price == other.price)
    else:
        result['reason'] = 'time_or_price_basis_not_aligned'
    return result


def public_config(database, quote, catalog):
    db = {key:value for key,value in asdict(database).items() if key != 'password'}
    return {'database':db,'providers':{'valuation':quote.valuation,'comparison':list(quote.comparison)},
            'scheduler':{k:getattr(quote,k) for k in ('operation_timeout_seconds','cycle_budget_seconds','max_retries','poll_interval_seconds',
                                                      'campaign_duration_days','post_close_observation_minutes','heartbeat_interval_seconds')},
            'tls':{'company_ca_file':quote.company_ca_file,'relaxed_providers':list(quote.relaxed_providers),
                   'relaxed_sources':list(catalog.relaxed_sources)},
            'instruments':{'max_age_hours':catalog.max_age_hours,'operation_timeout_seconds':catalog.operation_timeout_seconds}}


def execute(input_path, config_path, output_path):
    # Parse the entire input before configuration, database or provider access.
    from stock_quote_fetcher.config import ConfigurationError
    try:
        text = input_path.read_text(encoding='utf-8-sig')
    except (OSError,UnicodeError):
        raise ConfigurationError('無法讀取持股 CSV；請核對路徑、權限與 UTF-8 編碼。') from None
    holdings = parse_holdings(text)
    database, config = load_database_config(config_path), load_quote_config(config_path)
    catalog = load_instrument_catalog_config(config_path)
    from stock_quote_fetcher.config import _load_document, ConfigurationError
    from stock_quote_fetcher.storage import configuration_snapshot
    try:
        configuration_snapshot(_load_document(config_path))
    except ValueError:
        raise ConfigurationError('設定含不支援欄位，無法保存可重現快照。') from None
    run_id = uuid4()
    with Storage(database) as storage:
        storage.acquire_lock()
        storage.check_schema()
        generation, entries = storage.load_instrument_catalog()
        resolved, issues = resolve_holdings(holdings,entries)
        if len({i.instrument_id for i in resolved.values()}) != len(resolved):
            raise ConfigurationError('多個輸入代碼對應同一標的；請合併持股並保留一種代碼。')
        # Warm calendars before starting bounded network cycles.
        for holding in holdings:
            from stock_quote_fetcher.quality import timezone
            bounds(holding.market,datetime.now(UTC).astimezone(timezone(holding.market)).date())
        storage.recover_incomplete()
        storage.start_run(run_id,input_text=text,config=public_config(database,config,catalog),image_id=runtime_image_id())
        runner = QuoteRunner(storage,config)
        reports, comparisons = runner.run(run_id,holdings,resolved,issues)
    # All database commits succeeded. Output cannot claim uncommitted values.
    directory = output_path / str(run_id)
    directory.mkdir(parents=True,exist_ok=False)
    document = {'run_id':str(run_id),'catalog_generation':str(generation['id']),
                'cycles':[],'attempts':runner.events,'comparisons':comparisons,
                'statistics_boundary':'Adapter operations; Yahoo SDK internal HTTP retries/cache are not separately observable.'}
    final_attempts = {(event['ticker'],event['provider']):event for event in runner.events}
    exit_code = 3 if any(event['status'] != 'success' for event in final_attempts.values()) else 0
    for cycle, report in reports:
        data = report.to_dict()
        document['cycles'].append({'cycle_id':str(cycle),**data})
        target = directory / str(cycle)
        target.mkdir()
        with (target/'holdings.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(data['holdings'][0]))
            writer.writeheader()
            for row in data['holdings']:
                writer.writerow({**row,'quality_flags':'|'.join(row['quality_flags'])})
        for summary in data['summaries']:
            if summary['completeness'] != 'complete':
                exit_code = 3
    (directory/'summary.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return exit_code, directory, document

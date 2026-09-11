"""Local portfolio service. Its schema and collector lock are separate from the POC."""
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from io import StringIO
import csv
from threading import Lock, Thread
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from stock_quote_fetcher.config import load_database_config, load_quote_config, load_instrument_catalog_config
from stock_quote_fetcher.instruments import resolve_holdings
from stock_quote_fetcher.otc_catalog import supplement
from stock_quote_fetcher.models import Instrument, QualityFlag as F
from stock_quote_fetcher.quality import assess
from stock_quote_fetcher.quoting import QuoteRunner, public_config
from stock_quote_fetcher.storage import Storage, StorageError
from stock_quote_fetcher.valuation import value_holdings, exact_product, exact_sum, display_amount
from stock_quote_fetcher.web_input import WebError, validate_rows, normalize


def now():
    return datetime.now(UTC).isoformat()


def amount(value):
    return None if value is None else display_amount(value)


def ratio(value, denominator):
    with localcontext() as ctx:
        ctx.prec = 80
        return amount(value / denominator * 100) if denominator else None


def calculate(holdings, quotes, fx, names=None, market='ALL'):
    holdings = tuple(h for h in holdings if market == 'ALL' or h.market == market)
    if not holdings:
        return {'rows': [], 'summaries': [], 'chart': [], 'total': None, 'known_total': None,
                'cost': None, 'profit': None, 'return_pct': None, 'status': 'unavailable',
                'coverage': 0, 'count': 0, 'missing': [], 'needs_fx': False}
    report = value_holdings(holdings, quotes)
    output = report.to_dict()
    needs_fx = any(h.currency == 'USD' for h in holdings) and fx is None
    rows, values, costs = [], [], []
    for valued, row in zip(report.rows, output['holdings']):
        h = valued.holding
        factor = Decimal(1) if h.currency == 'TWD' else fx
        cost = exact_product(h.quantity, h.buy_price)
        value = valued.market_value
        twd = exact_product(value, factor) if value is not None and factor is not None else None
        twd_cost = exact_product(cost, factor) if factor is not None else None
        profit = exact_sum([value, cost.copy_negate()]) if value is not None else None
        if twd is not None:
            values.append(twd)
        if twd_cost is not None:
            costs.append(twd_cost)
        rows.append(dict(row, name=(names or {}).get(h.ticker, h.ticker), cost=amount(cost),
                         profit=amount(profit), return_pct=ratio(profit, cost) if profit is not None else None,
                         twd_value=amount(twd), twd_cost=amount(twd_cost), _exact=twd))
    coverage = sum(r.market_value is not None for r in report.rows)
    complete = coverage == len(holdings) and not needs_fx
    known = exact_sum(values) if values and not needs_fx else None
    total_cost = exact_sum(costs) if not needs_fx else None
    total_profit = exact_sum([known, total_cost.copy_negate()]) if complete else None
    chart = []
    for row in rows:
        value = row.pop('_exact')
        row['weight'] = ratio(value, known) if value is not None and known else None
        if row['weight'] is not None:
            chart.append({'ticker': row['ticker'], 'name': row['name'], 'value': amount(value), 'weight': row['weight'], '_exact': value})
    chart.sort(key=lambda r: r['_exact'], reverse=True)
    limit = 15 if market == 'ALL' else 10
    if len(chart) > limit:
        rest = chart[limit:]
        other = exact_sum([r['_exact'] for r in rest])
        chart = chart[:limit] + [{'ticker': '其他', 'name': '其他', 'value': amount(other), 'weight': ratio(other, known), '_exact': other, 'members': [r['ticker'] for r in rest]}]
    for item in chart:
        item.pop('_exact')
    status = 'unavailable' if not coverage or needs_fx else 'partial' if not complete else 'degraded' if any(r.degraded for r in report.rows) else 'complete'
    return {'rows': rows, 'summaries': output['summaries'], 'chart': chart,
            'total': amount(known) if complete else None, 'known_total': amount(known), 'cost': amount(total_cost),
            'profit': amount(total_profit), 'return_pct': ratio(total_profit, total_cost) if complete else None,
            'status': status, 'coverage': coverage, 'count': len(holdings), 'needs_fx': needs_fx,
            'missing': [r.holding.ticker for r in report.rows if r.market_value is None]}


class Dashboard:
    def __init__(self, config_path, schema='dashboard'):
        self.source = load_database_config(config_path)
        if schema == self.source.schema:
            raise WebError('儀表板 schema 必須與觀測 schema 不同。')
        self.db = replace(self.source, schema=schema)
        self.quote_config = replace(load_quote_config(config_path), comparison=())
        self.catalog_config = load_instrument_catalog_config(config_path)
        self.mutex = Lock()

    def initialize(self):
        """Explicit command only; never part of HTTP startup."""
        with Storage(self.db) as s:
            s.migrate()
            with s.transaction():
                s.conn.execute(sql.SQL('CREATE TABLE IF NOT EXISTS {} (id integer PRIMARY KEY CHECK(id=1), document jsonb NOT NULL)').format(s.table('portfolio')))
                s.conn.execute(sql.SQL('INSERT INTO {} VALUES (1,%s) ON CONFLICT DO NOTHING').format(s.table('portfolio')),
                               (Jsonb({'revision': 0, 'rows': [], 'fx': None, 'fx_updated_at': None}),))
                s.conn.execute(sql.SQL('CREATE TABLE IF NOT EXISTS {} (id text PRIMARY KEY, document jsonb NOT NULL)').format(s.table('refresh_jobs')))

    def get(self):
        with Storage(self.db) as s:
            row = s.conn.execute(sql.SQL('SELECT document FROM {} WHERE id=1').format(s.table('portfolio'))).fetchone()
            return row['document']

    def catalog(self):
        # Prefer the dedicated catalog; source POC is read-only and never locked.
        for config in (self.db, self.source):
            try:
                with Storage(config) as s:
                    return s.load_instrument_catalog()[1]
            except StorageError:
                continue
        raise WebError('官方標的清單暫不可用，請按「更新股票清單」後重試；編輯內容仍保留。', code='catalog_unavailable', status=503)

    def resolve(self, holdings):
        entries = supplement(self.catalog())
        resolved, issues = resolve_holdings(holdings, entries)
        if issues:
            raise WebError('部分標的無法識別，整份清單尚未儲存。', issues=[{'row': h.source_line, 'field': 'ticker', 'message': f'{h.ticker}：目前清單無法識別。請確認代碼；OTC／ADR 僅支援已核實的補充標的，不代表此股票不存在。'} for h in holdings if any(i.ticker == h.ticker for i in issues)])
        if len({i.instrument_id for i in resolved.values()}) != len(resolved):
            raise WebError('多個代碼對應相同股票，請合併成一列。')
        names = {h.ticker: next(e.name for e in entries if e.instrument_id == resolved[h.ticker].instrument_id) for h in holdings}
        return resolved, names

    def save(self, body):
        if not isinstance(body, dict) or type(body.get('revision')) is not int:
            raise WebError('缺少清單版本。')
        holdings = validate_rows(body.get('rows'))
        if holdings:
            resolved, names = self.resolve(holdings)
        else:
            resolved, names = {}, {}
        fx = body.get('fx')
        if fx in ('', None):
            fx = None
        else:
            from stock_quote_fetcher.input import positive_decimal
            if not isinstance(fx, str) or len(fx) > 24:
                raise WebError('匯率格式錯誤。')
            try:
                n = positive_decimal(fx, 'USD/TWD')
                if n > 10000 or n.as_tuple().exponent < -8:
                    raise ValueError('匯率最多 8 位小數且不得超過 10000。')
                fx = str(n)
            except ValueError as exc:
                raise WebError(str(exc)) from None
        with Storage(self.db) as s, s.conn.transaction():
            old = s.conn.execute(sql.SQL('SELECT document FROM {} WHERE id=1 FOR UPDATE').format(s.table('portfolio'))).fetchone()['document']
            if body['revision'] != old['revision']:
                raise WebError('持股已在另一個視窗更新。請重新載入後再編輯。', code='revision_conflict', status=409)
            document = {'revision': old['revision'] + 1, 'rows': normalize(holdings), 'names': names,
                        'instruments': {ticker: {'instrument_id': i.instrument_id, 'ticker': i.ticker,
                            'market': i.market.value, 'currency': i.currency, 'provider_symbols': dict(i.provider_symbols),
                            'exchange': i.exchange, 'asset_type': i.asset_type} for ticker, i in resolved.items()},
                        'fx': fx, 'fx_source': 'manual' if fx else None,
                        'fx_updated_at': now() if fx != old['fx'] else old.get('fx_updated_at'), 'saved_at': now()}
            s.conn.execute(sql.SQL('UPDATE {} SET document=%s WHERE id=1').format(s.table('portfolio')), (Jsonb(document),))
        return document

    def valuation(self, market='ALL'):
        if market not in ('ALL', 'TW', 'US'):
            raise WebError('市場篩選無效。')
        p = self.get()
        holdings = validate_rows(p['rows'])
        quotes, warning, candidates = {}, None, {}
        if holdings:
            try:
                # Saved official identities remain usable when catalogs are offline/expired.
                if p.get('instruments'):
                    resolved = {ticker: Instrument(**data) for ticker, data in p['instruments'].items()}
                else:
                    resolved, _ = self.resolve(holdings)
                for config in (self.db, self.source):
                    with Storage(config) as s:
                        for h in holdings:
                            for _, q in s.cached_quotes(resolved[h.ticker], 'yahoo'):
                                if q.provider_symbol != resolved[h.ticker].provider_symbols['yahoo'] or q.received_at > datetime.now(UTC):
                                    continue
                                checked = assess(q, as_of=datetime.now(UTC))
                                checked = replace(checked, quality_flags=checked.quality_flags | {F.CACHED})
                                if value_holdings([h], {h.ticker: checked}).rows[0].market_value is not None:
                                    candidates.setdefault(h.ticker, []).append(checked)
                                    break
                quotes = {ticker: max(items, key=lambda q: q.received_at) for ticker, items in candidates.items()}
            except (StorageError, WebError) as exc:
                warning = str(exc)
            quotes = {ticker: max(items, key=lambda q: q.received_at) for ticker, items in candidates.items()}
        result = calculate(holdings, quotes, Decimal(p['fx']) if p['fx'] else None, p.get('names'), market)
        result.update(portfolio_revision=p['revision'], valuation_id=str(uuid4()), computed_at=now(), market=market,
                      fx=p['fx'], fx_source=p.get('fx_source'), fx_updated_at=p.get('fx_updated_at'), warning=warning)
        return result

    def job(self, job_id):
        with Storage(self.db) as s:
            row = s.conn.execute(sql.SQL('SELECT document FROM {} WHERE id=%s').format(s.table('refresh_jobs')), (job_id,)).fetchone()
            if not row:
                raise WebError('找不到更新工作。', status=404)
            return row['document']

    def put_job(self, job):
        with Storage(self.db) as s:
            s.conn.execute(sql.SQL('INSERT INTO {} VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET document=EXCLUDED.document').format(s.table('refresh_jobs')), (job['job_id'], Jsonb(job)))

    def refresh(self, catalog_only=False):
        with self.mutex:
            p = self.get()
            if not p['rows'] and not catalog_only:
                raise WebError('請先保存持股。')
            with Storage(self.db) as s:
                jobs = s.conn.execute(sql.SQL('SELECT document FROM {} ORDER BY document->>\'created_at\' DESC LIMIT 1').format(s.table('refresh_jobs'))).fetchall()
            if jobs:
                latest = jobs[0]['document']
                if latest['status'] in ('queued', 'running'):
                    return latest
                if (datetime.now(UTC) - datetime.fromisoformat(latest['created_at'])).total_seconds() < 60:
                    raise WebError('更新冷卻中，請於一分鐘後重試。', code='cooldown', status=429)
            job = {'job_id': str(uuid4()), 'portfolio_revision': p['revision'], 'created_at': now(), 'status': 'queued', 'message': '等待更新', 'catalog_only': catalog_only}
            self.put_job(job)
            Thread(target=self.run_job, args=(job, p), daemon=True).start()
            return job

    def run_job(self, job, p):
        try:
            job.update(status='running', message='正在取得一般交易時段報價')
            self.put_job(job)
            try:
                self.catalog()
                needs_catalog = False
            except WebError:
                needs_catalog = True
            if job.get('catalog_only') or needs_catalog:
                from stock_quote_fetcher.catalog import fetch_all
                job.update(message='正在更新官方股票清單')
                self.put_job(job)
                with Storage(self.db) as s:
                    s.acquire_lock()
                    s.save_instrument_catalog(fetch_all(self.catalog_config), max_age_hours=self.catalog_config.max_age_hours)
                if job.get('catalog_only'):
                    job.update(status='succeeded', message='官方股票清單已更新，可以重新儲存持股。')
                    return
            holdings = validate_rows(p['rows'])
            resolved, _ = self.resolve(holdings)
            with Storage(self.db) as s:
                s.acquire_lock()
                s.recover_incomplete()
                runner = QuoteRunner(s, replace(self.quote_config, cycle_budget_seconds=300))
                runner.restore_cooldowns(s.provider_cooldowns(as_of=datetime.now(UTC)))
                count = 0
                # Every position gets a bounded batch; large portfolios cannot starve
                # later tickers behind a single market cycle's time budget.
                for offset in range(0, len(holdings), 5):
                    batch = holdings[offset:offset + 5]
                    stream = StringIO(newline='')
                    writer = csv.writer(stream)
                    writer.writerow(('ticker', 'quantity', 'buy_price'))
                    writer.writerows((h.ticker, h.quantity, h.buy_price) for h in batch)
                    run = uuid4()
                    s.start_run(run, input_text=stream.getvalue(), config=public_config(self.db, runner.config, self.catalog_config), image_id='dashboard-v1')
                    reports, _ = runner.run(run, batch, resolved, ())
                    count += sum(row.market_value is not None for _, report in reports for row in report.rows)
                    job.update(message=f'已處理 {offset + len(batch)}/{len(holdings)} 檔，正在更新')
                    self.put_job(job)
            job.update(status='succeeded' if count == len(holdings) else 'partial' if count else 'failed',
                       message=f'已完成：{count}/{len(holdings)} 檔有可用報價')
        except StorageError:
            job.update(status='failed', message='報價程序忙碌或資料庫暫不可用；保留既有價格，請稍後重試。')
        except Exception:
            job.update(status='failed', message='報價來源或官方清單暫不可用；保留既有價格，請稍後重試。')
        finally:
            job['completed_at'] = now()
            self.put_job(job)

    def recover_jobs(self):
        with Storage(self.db) as s:
            rows = s.conn.execute(sql.SQL("SELECT document FROM {} WHERE document->>'status' IN ('queued','running')").format(s.table('refresh_jobs'))).fetchall()
        for row in rows:
            job = row['document']
            job.update(status='failed', message='服務重啟中斷更新；請重新更新。', completed_at=now())
            self.put_job(job)

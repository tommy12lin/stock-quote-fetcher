"""Short PostgreSQL transactions on one session; no automatic reconnect or migration."""

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from datetime import timedelta
from hashlib import sha256
from importlib.metadata import version
from importlib.resources import files
import json
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stock_quote_fetcher.config import DatabaseConfig
from stock_quote_fetcher.input import parse_holdings
from stock_quote_fetcher.models import Quote, QualityFlag, utc_timestamp
from stock_quote_fetcher.valuation import value_holdings


class StorageError(RuntimeError):
    pass


TABLES = ('campaigns', 'scheduled_cycles', 'runs', 'holdings', 'cycles', 'fetch_attempts', 'quotes', 'valuations', 'valuation_totals',
          'instrument_catalog_generations', 'catalog_instruments')


def now():
    return datetime.now(UTC)


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def lock_key(schema: str) -> int:
    return int.from_bytes(sha256(f'stock-quote-fetcher:collector:{schema}'.encode()).digest()[:8], 'big', signed=True)


def configuration_snapshot(config: dict) -> tuple[dict, str]:
    # Explicit public sections/keys only. Never copy arbitrary environment or secrets.
    allowed = {
        'database': {'host','port','name','schema','user','connect_timeout','statement_timeout_ms','lock_timeout_ms'},
        'providers': {'valuation','comparison'},
        'scheduler': {'poll_interval_seconds','operation_timeout_seconds','cycle_budget_seconds','max_retries'},
        'tls': {'company_ca_file','relaxed_providers','relaxed_sources'},
        'instruments': {'max_age_hours','operation_timeout_seconds'},
    }
    result = {}
    for section, keys in allowed.items():
        values = config.get(section, {})
        if not isinstance(values, dict) or set(values) - keys:
            raise ValueError('Only documented public configuration fields may be snapshotted.')
        for value in values.values():
            if not (type(value) in (str, int, bool) or (isinstance(value, list) and all(type(item) is str for item in value))):
                raise ValueError('Configuration snapshot contains unsupported values.')
        result[section] = dict(values)
    if set(config) - allowed.keys():
        raise ValueError('Unknown configuration section.')
    encoded = json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return json.loads(encoded), digest(encoded.encode())


def migration_sources():
    root = files('stock_quote_fetcher').joinpath('migrations')
    return [(item.name, item.read_text(encoding='utf-8')) for item in sorted(root.iterdir(), key=lambda item: item.name) if item.name.endswith('.sql')]


class Storage:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.conn = None
        self.locked = False
        self.failed = False
        self.reading = False

    def __enter__(self):
        if self.conn is not None:
            raise StorageError('Storage session 不可重複開啟。')
        c = self.config
        try:
            self.conn = psycopg.connect(host=c.host, port=c.port, dbname=c.name, user=c.user,
                password=c.password, connect_timeout=c.connect_timeout, autocommit=True, row_factory=dict_row,
                options=f'-c timezone=UTC -c statement_timeout={c.statement_timeout_ms} -c lock_timeout={c.lock_timeout_ms}')
            # Explicitly qualified application SQL; never trust a caller's search_path.
            self.conn.execute("SET search_path TO pg_catalog")
            return self
        except psycopg.Error:
            if self.conn:
                self.conn.close()
            raise StorageError('資料庫連線失敗；請核對網路、帳號與環境設定。') from None

    def __exit__(self, *args):
        if self.conn:
            self.conn.close()  # Session locks released even on error.
        self.locked = False

    def table(self, name):
        return sql.Identifier(self.config.schema, name)

    @contextmanager
    def transaction(self, *, writer=True, readonly=False):
        if self.failed or self.conn is None or self.conn.closed:
            raise StorageError('儲存連線已失效；必須結束本次執行。')
        if writer and not self.locked:
            raise StorageError('寫入前必須取得收集程序鎖。')
        try:
            with self.conn.transaction():
                if readonly:
                    self.conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                yield
        except psycopg.Error as exc:
            self.failed = True
            # Do not expose server text: it may contain credentials, data, or DSN.
            raise StorageError(f'資料庫操作失敗（SQLSTATE {exc.sqlstate or "unknown"}）；結果可能未知，請依原 UUID 查核。') from None

    def check_permissions(self, *, migration=False):
        with self.transaction(writer=False, readonly=True):
            row = self.conn.execute("""SELECT current_database() AS database, current_user AS username,
                current_setting('server_version') AS server_version,
                r.rolsuper, r.rolcreatedb, r.rolcreaterole,
                has_database_privilege(current_user,current_database(),'CONNECT') AS connect,
                has_schema_privilege(current_user,%s,'USAGE') AS usage,
                has_schema_privilege(current_user,%s,'CREATE') AS create
                FROM pg_roles r WHERE rolname=current_user""", (self.config.schema, self.config.schema)).fetchone()
            if any(row[key] for key in ('rolsuper','rolcreatedb','rolcreaterole')) or not row['connect'] or not row['usage'] or (migration and not row['create']):
                raise StorageError('專用帳號權限不符：禁止管理權限，需 CONNECT／USAGE；migration 另需 CREATE。')
            return row

    def acquire_lock(self):
        if self.locked:
            return
        self.check_permissions()
        with self.transaction(writer=False):
            acquired = self.conn.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (lock_key(self.config.schema),)).fetchone()['acquired']
        if not acquired:
            raise StorageError('另一個收集程序或 migration 正在使用此 database／schema。')
        self.locked = True

    def _versions(self):
        exists = self.conn.execute('SELECT to_regclass(%s) AS relation', (f'{self.config.schema}.schema_migrations',)).fetchone()['relation']
        if exists is None:
            return []
        return self.conn.execute(sql.SQL('SELECT version,checksum FROM {} ORDER BY version').format(self.table('schema_migrations'))).fetchall()

    def _check_versions(self, *, require_current):
        sources = migration_sources()
        expected = [(name, digest(body.encode())) for name, body in sources]
        actual = [(r['version'], r['checksum']) for r in self._versions()]
        if actual != expected[:len(actual)] or (require_current and actual != expected):
            raise StorageError('Schema 版本或 migration checksum 不符；請先執行正確版本的 migration。')
        return sources[len(actual):]

    def migrate(self):
        self.check_permissions(migration=True)
        self.acquire_lock()
        with self.transaction():
            pending = self._check_versions(require_current=False)
        applied = []
        for name, body in pending:
            with self.transaction():
                self.conn.execute(sql.SQL('CREATE TABLE IF NOT EXISTS {} (version text PRIMARY KEY, checksum text NOT NULL, package_version text NOT NULL, applied_at timestamptz NOT NULL)').format(self.table('schema_migrations')))
                self.conn.execute(sql.SQL(body).format(schema=sql.Identifier(self.config.schema)))
                self._insert('schema_migrations', dict(version=name, checksum=digest(body.encode()), package_version=version('stock-quote-fetcher'), applied_at=now()))
            applied.append(name)
        return applied

    def check_schema(self):
        with self.transaction(writer=False, readonly=True):
            self._check_versions(require_current=True)
            for table in TABLES:
                # PostgreSQL privilege lists mean ANY; check each privilege explicitly.
                for privilege in ('SELECT','INSERT','UPDATE'):
                    if not self.conn.execute('SELECT has_table_privilege(current_user,%s,%s) AS permitted', (f'{self.config.schema}.{table}', privilege)).fetchone()['permitted']:
                        raise StorageError('資料表權限不完整。')

    def _insert(self, table, record):
        self.conn.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(self.table(table),
            sql.SQL(',').join(map(sql.Identifier, record)), sql.SQL(',').join(sql.Placeholder() for _ in record)), tuple(record.values()))

    def _one(self, table, identity):
        row = self.conn.execute(sql.SQL('SELECT * FROM {} WHERE id=%s').format(self.table(table)), (identity,)).fetchone()
        if row is None:
            raise ValueError(f'{table} UUID does not exist.')
        return row

    def _running(self, table, identity):
        row = self._one(table, identity)
        if row['status'] != 'running':
            raise ValueError(f'{table} is not running.')
        return row

    def create_campaign(self, identity, *, input_text, config, planned_start, planned_end,
                        scheduled_cycles, source_instruments, calendar_version, schedule_version,
                        threshold_version, maintenance_windows):
        self.check_schema()
        parse_holdings(input_text)
        snapshot, config_hash = configuration_snapshot(config)
        start, end = utc_timestamp(planned_start), utc_timestamp(planned_end)
        with self.transaction():
            self._insert('campaigns', dict(id=identity, planned_start=start, planned_end=end, status='running',
                input_snapshot=input_text, input_hash=digest(input_text.encode()), config_snapshot=Jsonb(snapshot), config_hash=config_hash,
                source_instruments=Jsonb(source_instruments), calendar_version=calendar_version, schedule_version=schedule_version,
                threshold_version=threshold_version, maintenance_windows=Jsonb(maintenance_windows)))
            for cycle in scheduled_cycles:
                stamp = utc_timestamp(cycle['scheduled_at'])
                if not start <= stamp < end:
                    raise ValueError('Scheduled cycle lies outside campaign.')
                self._insert('scheduled_cycles', dict(id=cycle['id'], campaign_id=identity, market=cycle['market'], scheduled_at=stamp, window_type=cycle['window_type']))

    def start_run(self, identity, *, input_text, config, image_id, campaign_id=None):
        if not self.locked:
            raise StorageError('寫入前必須取得收集程序鎖。')
        self.check_schema()
        holdings = parse_holdings(input_text)
        snapshot, config_hash = configuration_snapshot(config)
        input_hash = digest(input_text.encode())
        with self.transaction():
            if campaign_id:
                campaign = self._running('campaigns', campaign_id)
                if campaign['input_hash'] != input_hash or campaign['config_hash'] != config_hash:
                    raise ValueError('Campaign input/configuration is immutable; create a new campaign.')
            stamp = now()
            self._insert('runs', dict(id=identity, campaign_id=campaign_id, started_at=stamp, heartbeat_at=stamp, status='running',
                package_version=version('stock-quote-fetcher'), image_id=image_id, input_snapshot=input_text, input_hash=input_hash,
                config_snapshot=Jsonb(snapshot), config_hash=config_hash))
            ids = {}
            for holding in holdings:
                ids[holding.ticker] = uuid4()
                self._insert('holdings', dict(id=ids[holding.ticker], run_id=identity, ticker=holding.ticker, market=holding.market.value,
                    currency=holding.currency, buy_price=holding.buy_price, quantity=holding.quantity))
        return ids

    def start_cycle(self, identity, run_id, *, market, scheduled_at, scheduled_cycle_id=None):
        stamp = utc_timestamp(scheduled_at)
        with self.transaction():
            run = self._running('runs', run_id)
            if scheduled_cycle_id:
                scheduled = self._one('scheduled_cycles', scheduled_cycle_id)
                if (scheduled['campaign_id'], scheduled['market'], scheduled['scheduled_at']) != (run['campaign_id'], market, stamp):
                    raise ValueError('Scheduled cycle does not match run/campaign/market/time.')
            self._insert('cycles', dict(id=identity, run_id=run_id, campaign_id=run['campaign_id'], scheduled_cycle_id=scheduled_cycle_id,
                market=market, scheduled_at=stamp, started_at=now(), status='running'))

    def start_attempt(self, identity, cycle_id, *, provider, instrument_id, ticker, attempt_number):
        with self.transaction():
            cycle = self._running('cycles', cycle_id)
            self._running('runs', cycle['run_id'])
            if not self.conn.execute(sql.SQL('SELECT 1 FROM {} WHERE run_id=%s AND ticker=%s AND market=%s').format(self.table('holdings')),
                                     (cycle['run_id'], ticker, cycle['market'])).fetchone():
                raise ValueError('Attempt ticker does not belong to cycle market/run.')
            self._insert('fetch_attempts', dict(id=identity, run_id=cycle['run_id'], cycle_id=cycle_id, provider=provider,
                instrument_id=instrument_id, ticker=ticker, attempt_number=attempt_number, started_at=now(), status='started'))

    def finish_attempt(self, identity, result, *, elapsed_ms, quote_id=None, source_timezone=None, source_time_raw=None, provider_evidence=None):
        with self.transaction():
            attempt = self._one('fetch_attempts', identity)
            self._running('cycles', attempt['cycle_id'])
            self._running('runs', attempt['run_id'])
            if attempt['status'] != 'started' or (result.instrument_id, result.provider) != (attempt['instrument_id'], attempt['provider']):
                raise ValueError('Attempt state or result identity mismatch.')
            status = result.status.value
            error_code = None if status == 'success' else status
            evidence = None
            quote = result.quote
            if quote:
                if quote.ticker != attempt['ticker']:
                    raise ValueError('Quote ticker does not match attempt.')
                if not quote.price.is_finite() or quote.price <= 0:
                    status, error_code = 'invalid_payload', 'invalid_price'
                    evidence = {'invalid_price': str(quote.price)}
                    quote = None
                elif quote_id is None:
                    raise ValueError('Caller must allocate quote UUID before submitting result.')
            if quote:
                record = asdict(quote)
                record['quality_flags'] = Jsonb(sorted(record['quality_flags']))
                record.update(id=quote_id, attempt_id=identity, source_timezone=source_timezone, source_time_raw=source_time_raw)
                self._insert('quotes', record)
            # Save normalized evidence, not exception messages or raw provider payloads.
            if evidence is None:
                evidence = {'status': status}
                if quote:
                    evidence.update(ticker=quote.ticker, provider_symbol=quote.provider_symbol, price=str(quote.price),
                        received_at=quote.received_at.isoformat(), quote_time=quote.quote_time.isoformat() if quote.quote_time else None)
            if provider_evidence is not None:
                # Only pass adapter-produced, whitelisted evidence, never raw exceptions.
                evidence['adapter'] = provider_evidence
            response_hash = digest(json.dumps(evidence, sort_keys=True).encode())
            self.conn.execute(sql.SQL('UPDATE {} SET status=%s,completed_at=%s,elapsed_ms=%s,error_code=%s,response_hash=%s,response_evidence=%s WHERE id=%s').format(self.table('fetch_attempts')),
                (status, now(), elapsed_ms, error_code, response_hash, Jsonb(evidence), identity))
        return quote_id if quote else None

    def cached_quotes(self, instrument, provider):
        """Candidate history is revalidated by the caller against today's calendar."""
        with self.transaction(writer=False, readonly=True):
            rows = self.conn.execute(sql.SQL('''SELECT * FROM {} WHERE instrument_id=%s
                AND provider=%s AND ticker=%s AND currency=%s AND market=%s
                ORDER BY received_at DESC LIMIT 20''').format(self.table('quotes')),
                (instrument.instrument_id,provider,instrument.ticker,instrument.currency,instrument.market.value)).fetchall()
        return [(row['id'],Quote(**{key:row[key] for key in Quote.__dataclass_fields__})) for row in rows]

    def finish_cycle(self, identity, *, selected_quotes, quality_flags=None):
        """Recompute valuations from persisted holdings/quotes; caller chooses sources/cache."""
        from stock_quote_fetcher.models import Holding
        with self.transaction():
            cycle = self._running('cycles', identity)
            self._running('runs', cycle['run_id'])
            if self.conn.execute(sql.SQL("SELECT 1 FROM {} WHERE cycle_id=%s AND status='started' LIMIT 1").format(self.table('fetch_attempts')), (identity,)).fetchone():
                raise ValueError('Cannot complete cycle with unfinished attempts.')
            stored = self.conn.execute(sql.SQL('SELECT * FROM {} WHERE run_id=%s AND market=%s ORDER BY ticker').format(self.table('holdings')), (cycle['run_id'],cycle['market'])).fetchall()
            holdings = [Holding(r['ticker'],r['market'],r['buy_price'],r['quantity']) for r in stored]
            if set(selected_quotes) - {h.ticker for h in holdings}:
                raise ValueError('Selected quote refers to unknown holding.')
            quotes = {}
            quality_flags = quality_flags or {}
            if set(quality_flags) - set(selected_quotes):
                raise ValueError('Quality flags require a selected quote.')
            for ticker, quote_id in selected_quotes.items():
                if quote_id is None:
                    continue
                record = self._one('quotes', quote_id)
                origin = self._one('fetch_attempts', record['attempt_id'])
                flags = set(record['quality_flags']) | {QualityFlag(flag) for flag in quality_flags.get(ticker, ())}
                if origin['cycle_id'] != identity:
                    flags.add(QualityFlag.CACHED)
                # Original quote remains immutable; usage-specific flags go on valuation.
                quotes[ticker] = replace(Quote(**{key: record[key] for key in Quote.__dataclass_fields__}), quality_flags=frozenset(flags))
            report = value_holdings(holdings, quotes)
            for holding, row in zip(stored, report.rows, strict=True):
                self._insert('valuations', dict(cycle_id=identity, holding_id=holding['id'], run_id=cycle['run_id'],
                    quote_id=selected_quotes.get(holding['ticker']), market_value=row.market_value,
                    quality_flags=Jsonb(sorted(row.quality_flags)), failure_reason=row.failure_reason))
            for summary in report.summaries:
                self._insert('valuation_totals', dict(cycle_id=identity, **asdict(summary)))
            self.conn.execute(sql.SQL("UPDATE {} SET status='completed',completed_at=%s WHERE id=%s").format(self.table('cycles')), (now(),identity))
        return report

    def heartbeat(self, run_id):
        with self.transaction():
            self._running('runs', run_id)
            self.conn.execute(sql.SQL('UPDATE {} SET heartbeat_at=%s WHERE id=%s').format(self.table('runs')), (now(),run_id))

    def stop_cycle(self, identity, *, status, reason):
        if status not in {'interrupted','skipped'} or not reason or not reason.replace('_','').isalnum():
            raise ValueError('Use interrupted/skipped and a non-secret reason code.')
        with self.transaction():
            cycle = self._running('cycles',identity)
            self._running('runs',cycle['run_id'])
            self.conn.execute(sql.SQL("UPDATE {} SET status='interrupted',completed_at=%s,error_code='interrupted' WHERE cycle_id=%s AND status='started'").format(self.table('fetch_attempts')), (now(),identity))
            self.conn.execute(sql.SQL('UPDATE {} SET status=%s,reason=%s,completed_at=%s WHERE id=%s').format(self.table('cycles')), (status,reason,now(),identity))

    def finish_run(self, run_id):
        with self.transaction():
            self._running('runs', run_id)
            if self.conn.execute(sql.SQL("SELECT 1 FROM {} WHERE run_id=%s AND status='running' LIMIT 1").format(self.table('cycles')), (run_id,)).fetchone():
                raise ValueError('Run contains unfinished cycles.')
            self.conn.execute(sql.SQL("UPDATE {} SET status='completed',ended_at=%s WHERE id=%s").format(self.table('runs')), (now(),run_id))

    def recover_incomplete(self):
        """Only call after acquiring the shared lock, before creating the new run."""
        self.check_schema()
        stamp = now()
        with self.transaction():
            counts = {}
            for table, old in (('fetch_attempts','started'), ('cycles','running'), ('runs','running')):
                counts[table] = self.conn.execute(sql.SQL("UPDATE {} SET status='interrupted',recovered_at=%s WHERE status=%s").format(self.table(table)), (stamp,old)).rowcount
            return counts

    def save_instrument_catalog(self, fetched, *, max_age_hours):
        """Atomically publish one complete generation assembled from every source."""
        from stock_quote_fetcher.catalog import SOURCES
        expected = {spec.name for spec in SOURCES}
        if {item.source for item in fetched} != expected or len(fetched) != len(expected):
            raise ValueError('A catalog generation requires each configured official source exactly once.')
        combined = [(item.source, entry) for item in fetched for entry in item.entries]
        keys = [(entry.market, entry.ticker) for _, entry in combined]
        if len(set(keys)) != len(keys):
            raise ValueError('Official sources produce ambiguous canonical market/ticker rows.')
        identity, stamp = uuid4(), now()
        sources = [{
            'name': item.source, 'fetched_at': item.fetched_at.isoformat(),
            'payload_hash': item.payload_hash, 'byte_count': item.byte_count,
            'row_count': len(item.entries), 'tls_relaxed': item.tls_relaxed,
        } for item in fetched]
        with self.transaction():
            self._check_versions(require_current=True)
            self._insert('instrument_catalog_generations', dict(id=identity, created_at=stamp,
                completed_at=stamp, expires_at=stamp+timedelta(hours=max_age_hours), sources=Jsonb(sources)))
            for source, entry in combined:
                self._insert('catalog_instruments', dict(generation_id=identity, source=source,
                    instrument_id=entry.instrument_id, ticker=entry.ticker, market=entry.market.value,
                    currency=entry.currency, exchange=entry.exchange, asset_type=entry.asset_type,
                    name=entry.name, provider_symbols=Jsonb(dict(entry.provider_symbols)), aliases=Jsonb(list(entry.aliases))))
        return identity

    def load_instrument_catalog(self, *, as_of=None):
        from stock_quote_fetcher.instruments import CatalogInstrument
        stamp = now() if as_of is None else utc_timestamp(as_of)
        with self.transaction(writer=False, readonly=True):
            self._check_versions(require_current=True)
            generation = self.conn.execute(sql.SQL('SELECT * FROM {} WHERE completed_at<=%s AND expires_at>=%s ORDER BY completed_at DESC LIMIT 1').format(self.table('instrument_catalog_generations')), (stamp,stamp)).fetchone()
            if generation is None:
                raise StorageError('沒有可用且未過期的標的清單；請先執行 instruments-refresh。')
            rows = self.conn.execute(sql.SQL('SELECT * FROM {} WHERE generation_id=%s ORDER BY market,ticker').format(self.table('catalog_instruments')), (generation['id'],)).fetchall()
        return generation, tuple(CatalogInstrument(row['instrument_id'],row['ticker'],row['market'],row['currency'],
            row['exchange'],row['asset_type'],row['name'],row['provider_symbols'],tuple(row['aliases'])) for row in rows)

    @contextmanager
    def report_snapshot(self):
        if self.reading:
            raise StorageError('報告快照不可巢狀開啟。')
        with self.transaction(writer=False, readonly=True):
            self._check_versions(require_current=True)
            self.reading = True
            try:
                yield self
            finally:
                self.reading = False

    def read_run(self, run_id):
        """Call inside report_snapshot for a consistent multi-table export."""
        if not self.reading:
            raise StorageError('報告查詢必須在 report_snapshot 中執行。')
        result = {'run': self._one('runs', run_id)}
        for table in ('holdings','cycles','fetch_attempts','valuations'):
            result[table] = self.conn.execute(sql.SQL('SELECT * FROM {} WHERE run_id=%s').format(self.table(table)), (run_id,)).fetchall()
        result['totals'] = self.conn.execute(sql.SQL('SELECT t.* FROM {} t JOIN {} c ON c.id=t.cycle_id WHERE c.run_id=%s').format(self.table('valuation_totals'),self.table('cycles')), (run_id,)).fetchall()
        result['quotes'] = self.conn.execute(sql.SQL('SELECT q.* FROM {} q WHERE q.attempt_id IN (SELECT id FROM {} WHERE run_id=%s) OR q.id IN (SELECT quote_id FROM {} WHERE run_id=%s)').format(self.table('quotes'),self.table('fetch_attempts'),self.table('valuations')), (run_id,run_id)).fetchall()
        return result

    def read_campaign(self, campaign_id, *, as_of):
        if not self.reading:
            raise StorageError('報告查詢必須在 report_snapshot 中執行。')
        campaign = self._one('campaigns', campaign_id)
        # Left join preserves downtime opportunities; future opportunities stay distinguishable.
        schedule = self.conn.execute(sql.SQL('''SELECT s.*, c.id AS cycle_id,c.run_id,c.status AS cycle_status,
            (s.scheduled_at <= %s) AS due FROM {} s LEFT JOIN {} c ON c.scheduled_cycle_id=s.id
            WHERE s.campaign_id=%s ORDER BY s.scheduled_at,s.market''').format(self.table('scheduled_cycles'),self.table('cycles')),
            (utc_timestamp(as_of),campaign_id)).fetchall()
        runs = self.conn.execute(sql.SQL('SELECT id FROM {} WHERE campaign_id=%s ORDER BY started_at,id').format(self.table('runs')), (campaign_id,)).fetchall()
        return {'campaign':campaign,'scheduled_cycles':schedule,'runs':[self.read_run(row['id']) for row in runs]}

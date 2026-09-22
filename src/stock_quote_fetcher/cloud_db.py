"""Explicit cloud database administration; no maintenance on HTTP startup.

SQL output contains no credentials. Bootstrap runs as the schema's administrator,
while check/capacity use the restricted runtime account. Prune defaults to dry-run.
"""
import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import psycopg
from psycopg import sql

from stock_quote_fetcher.config import DatabaseConfig, load_database_config
from stock_quote_fetcher.storage import Storage, StorageError, TABLES, digest, lock_key, migration_sources

RUNTIME_TABLES = TABLES + ('portfolio', 'refresh_jobs')


def bootstrap_sql(schema='dashboard', runtime='finpo_app'):
    """Idempotent migrations followed by least-privilege grants; administrator owns DDL."""
    DatabaseConfig(schema=schema, password='validation-only')
    ns, role = sql.Identifier(schema), sql.Identifier(runtime)
    lines = [sql.SQL('BEGIN; SET LOCAL lock_timeout = \'3s\'; SET LOCAL statement_timeout = \'30s\';'),
             sql.SQL("DO $role$ BEGIN IF current_user = {} THEN RAISE EXCEPTION 'Use a separate administrator'; END IF; END $role$;").format(sql.Literal(runtime)),
             sql.SQL("DO $lock$ BEGIN IF NOT pg_try_advisory_xact_lock({}) THEN RAISE EXCEPTION 'Collector is active'; END IF; END $lock$;").format(sql.Literal(lock_key(schema))),
             sql.SQL('CREATE SCHEMA IF NOT EXISTS {};').format(ns),
             sql.SQL('CREATE TABLE IF NOT EXISTS {}.schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, package_version text NOT NULL, applied_at timestamptz NOT NULL);').format(ns)]
    # Fail closed on unknown or changed migrations before applying anything.
    names = [name for name, _ in migration_sources()]
    lines.append(sql.SQL("DO $guard$ BEGIN IF EXISTS (SELECT 1 FROM {}.schema_migrations WHERE NOT (version = ANY ({}))) THEN RAISE EXCEPTION 'Unknown migration'; END IF; END $guard$;").format(ns, sql.Literal(names)))
    for name, body in migration_sources():
        lines.append(sql.SQL("""DO $migration$ BEGIN
          IF EXISTS (SELECT 1 FROM {s}.schema_migrations WHERE version={v}) THEN
            IF NOT EXISTS (SELECT 1 FROM {s}.schema_migrations WHERE version={v} AND checksum={h}) THEN
              RAISE EXCEPTION 'Migration checksum mismatch';
            END IF;
          ELSE
            {body}
            INSERT INTO {s}.schema_migrations VALUES ({v},{h},'cloud-bootstrap',now());
          END IF;
        END $migration$;""").format(s=ns, v=sql.Literal(name), h=sql.Literal(digest(body.encode())),
                                      body=sql.SQL(body).format(schema=ns)))
    lines.extend([
        sql.SQL('CREATE TABLE IF NOT EXISTS {}.portfolio (id integer PRIMARY KEY CHECK(id=1), document jsonb NOT NULL);').format(ns),
        sql.SQL("INSERT INTO {}.portfolio VALUES (1,'{{\"revision\":0,\"rows\":[],\"fx\":null,\"fx_updated_at\":null}}') ON CONFLICT DO NOTHING;").format(ns),
        sql.SQL('CREATE TABLE IF NOT EXISTS {}.refresh_jobs (id text PRIMARY KEY, document jsonb NOT NULL);').format(ns),
        sql.SQL('ALTER SCHEMA {} OWNER TO CURRENT_USER;').format(ns),
        sql.SQL('REVOKE ALL ON SCHEMA {} FROM PUBLIC, {};').format(ns, role),
        sql.SQL('GRANT USAGE ON SCHEMA {} TO {};').format(ns, role),
    ])
    for name in RUNTIME_TABLES + ('schema_migrations',):
        table = sql.Identifier(schema, name)
        grants = sql.SQL('SELECT') if name == 'schema_migrations' else sql.SQL('SELECT, INSERT, UPDATE')
        lines.extend([sql.SQL('ALTER TABLE {} OWNER TO CURRENT_USER;').format(table),
                      sql.SQL('REVOKE ALL ON {} FROM PUBLIC, {};').format(table, role),
                      sql.SQL('GRANT {} ON {} TO {};').format(grants, table, role),
                      sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY;').format(table),
                      sql.SQL('DROP POLICY IF EXISTS runtime_access ON {};').format(table)])
        if name == 'schema_migrations':
            lines.append(sql.SQL('CREATE POLICY runtime_access ON {} FOR SELECT TO {} USING (true);').format(table, role))
        else:
            lines.append(sql.SQL('CREATE POLICY runtime_access ON {} FOR ALL TO {} USING (true) WITH CHECK (true);').format(table, role))
    for name in ('positive_decimal', 'nonnegative_decimal'):
        lines.append(sql.SQL('ALTER DOMAIN {} OWNER TO CURRENT_USER;').format(sql.Identifier(schema, name)))
    if schema != 'app':
        lines.append(sql.SQL("DO $source$ BEGIN IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='app') THEN REVOKE ALL ON SCHEMA app FROM {}; END IF; END $source$;").format(role))
    lines.append(sql.SQL('COMMIT;'))
    return '\n'.join(line.as_string() for line in lines)


def check_runtime(storage):
    row = storage.check_permissions()
    if row['create']:
        raise StorageError('Runtime 不得具有 schema CREATE 權限。')
    role = storage.conn.execute('SELECT rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
    if any(role.values()):
        raise StorageError('Runtime 不得具有 replication／bypassrls 權限。')
    storage.check_schema()
    for name in RUNTIME_TABLES + ('schema_migrations',):
        rls = storage.conn.execute('SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(%s)',
                                   (f'{storage.config.schema}.{name}',)).fetchone()
        if not rls or not rls['relrowsecurity']:
            raise StorageError('Runtime 資料表必須啟用 RLS。')
        required = {'SELECT'} if name == 'schema_migrations' else {'SELECT', 'INSERT', 'UPDATE'}
        for permission in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
            actual = storage.conn.execute('SELECT has_table_privilege(current_user,%s,%s) AS allowed',
                                          (f'{storage.config.schema}.{name}', permission)).fetchone()['allowed']
            if actual != (permission in required):
                raise StorageError('Runtime 資料表權限不符合最小權限契約。')
    return {'runtime_permissions': 'passed'}


def capacity(storage):
    rows = storage.conn.execute("""SELECT c.relname AS name, pg_table_size(c.oid) AS table_bytes,
        pg_indexes_size(c.oid) AS index_bytes, pg_total_relation_size(c.oid) AS total_bytes
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relkind='r' ORDER BY c.relname""", (storage.config.schema,)).fetchall()
    return {'database_bytes': storage.conn.execute('SELECT pg_database_size(current_database()) AS bytes').fetchone()['bytes'],
            'schema_bytes': sum(row['total_bytes'] for row in rows), 'tables': rows}


def prune(storage, *, days=30, apply=False, as_of=None):
    """Prune completed standalone evidence, retaining the exact cache candidate window.

    Preserve runs referenced by retained valuations transitively, the latest 20 quotes
    per cache key, all campaigns/live work, and the latest two catalog generations.
    All selection and deletion happen under the collector lock in one transaction.
    Runtime lacks DELETE; only the separate administrator may apply this operation.
    """
    if type(days) is not int or days < 7:
        raise ValueError('證據保存期不得少於 7 天。')
    stamp = as_of or datetime.now(UTC)
    cutoff = stamp - timedelta(days=days)
    t = storage.table
    with storage.conn.transaction():
        if not storage.conn.execute('SELECT pg_try_advisory_xact_lock(%s) AS locked', (lock_key(storage.config.schema),)).fetchone()['locked']:
            raise StorageError('收集工作正在執行，請稍後清理。')
        storage._check_versions(require_current=True)
        # Freeze the protected run graph before deleting any valuation edges.
        candidates = storage.conn.execute(sql.SQL("""WITH RECURSIVE
          cache AS (SELECT q.attempt_id, row_number() OVER (
            PARTITION BY instrument_id,provider,ticker,currency,market ORDER BY received_at DESC,id DESC) AS rank FROM {quotes} q),
          protected(id) AS (
            SELECT id FROM {runs} WHERE campaign_id IS NOT NULL OR status='running' OR ended_at IS NULL OR ended_at >= %s
            UNION
            SELECT a.run_id FROM {attempts} a JOIN cache ON cache.attempt_id=a.id WHERE cache.rank<=20
          ),
          kept(id) AS (
            SELECT id FROM protected
            UNION
            SELECT a.run_id FROM kept k JOIN {valuations} v ON v.run_id=k.id
              JOIN {quotes} q ON q.id=v.quote_id JOIN {attempts} a ON a.id=q.attempt_id
          )
          SELECT id FROM {runs} WHERE status IN ('completed','interrupted') AND campaign_id IS NULL
            AND ended_at < %s AND id NOT IN (SELECT id FROM kept) ORDER BY id""").format(
                quotes=t('quotes'), runs=t('runs'), attempts=t('fetch_attempts'), valuations=t('valuations')), (cutoff, cutoff)).fetchall()
        ids = [row['id'] for row in candidates]
        generations = storage.conn.execute(sql.SQL("""SELECT id FROM {g} WHERE completed_at < %s AND expires_at < %s
            AND id NOT IN (SELECT id FROM {g} ORDER BY completed_at DESC,id DESC LIMIT 2)""").format(g=t('instrument_catalog_generations')), (cutoff, stamp)).fetchall()
        generation_ids = [row['id'] for row in generations]
        jobs = storage.conn.execute(sql.SQL("""SELECT id FROM {} WHERE document->>'status' IN ('succeeded','partial','failed')
            AND (document->>'completed_at')::timestamptz < %s
            AND id <> (SELECT id FROM {} ORDER BY document->>'created_at' DESC NULLS LAST,id DESC LIMIT 1)""").format(t('refresh_jobs'), t('refresh_jobs')), (cutoff,)).fetchall()
        summary = {'apply': apply, 'days': days, 'runs': len(ids), 'catalog_generations': len(generation_ids), 'jobs': len(jobs)}
        if not apply:
            return summary
        # Foreign-key order; a referenced quote's origin run is retained by the graph.
        for name in ('valuations', 'valuation_totals', 'quotes', 'fetch_attempts', 'cycles', 'holdings', 'runs'):
            condition = {'valuation_totals': sql.SQL('cycle_id IN (SELECT id FROM {} WHERE run_id=ANY(%s))').format(t('cycles')),
                         'quotes': sql.SQL('attempt_id IN (SELECT id FROM {} WHERE run_id=ANY(%s))').format(t('fetch_attempts')),
                         'runs': sql.SQL('id=ANY(%s)')}.get(name, sql.SQL('run_id=ANY(%s)'))
            storage.conn.execute(sql.SQL('DELETE FROM {} WHERE {}').format(t(name), condition), (ids,))
        storage.conn.execute(sql.SQL('DELETE FROM {} WHERE generation_id=ANY(%s)').format(t('catalog_instruments')), (generation_ids,))
        storage.conn.execute(sql.SQL('DELETE FROM {} WHERE id=ANY(%s)').format(t('instrument_catalog_generations')), (generation_ids,))
        storage.conn.execute(sql.SQL('DELETE FROM {} WHERE id=ANY(%s)').format(t('refresh_jobs')), ([row['id'] for row in jobs],))
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('bootstrap-sql', 'check', 'capacity', 'prune'))
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--schema', default='dashboard')
    parser.add_argument('--runtime-role', default='finpo_app')
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.action == 'bootstrap-sql':
        print(bootstrap_sql(args.schema, args.runtime_role))
        return
    try:
        config = replace(load_database_config(args.config), schema=args.schema)
        with Storage(config) as storage:
            result = check_runtime(storage) if args.action == 'check' else capacity(storage) if args.action == 'capacity' else prune(storage, days=args.days, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
    except (StorageError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
    except psycopg.Error:
        parser.exit(1, '資料庫管理操作失敗；請確認管理者權限與 schema 狀態。\n')


if __name__ == '__main__':
    main()

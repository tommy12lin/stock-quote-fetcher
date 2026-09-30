"""C7-6: read back the official listing generations after an out-of-band refresh.

Read only. Carried base64-encoded in C76_PROBE for one execution of the c76-source-probe
Job, the same way scripts/c76_probe.py is, so the Supabase password stays in the Job.
Everything runs in one READ ONLY transaction and issues SELECTs only. Kept under docs/
so recording it does not trigger an image build (docs/cloud-phase-1-plan.md, image window).

Each output line is "C76 " plus one JSON object, like the probe.
"""
from base64 import b64decode
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from psycopg import sql

from stock_quote_fetcher.config import load_database_config
from stock_quote_fetcher.storage import Storage


def emit(kind, **fields):
    sys.stdout.write('C76 ' + json.dumps({'kind': kind, **fields}, ensure_ascii=False, default=str) + '\n')
    sys.stdout.flush()


config = replace(load_database_config(Path('/app/cloud.toml')), schema='dashboard')
with Storage(config) as s:
    with s.transaction(writer=False, readonly=True):
        g, c = s.table('instrument_catalog_generations'), s.table('catalog_instruments')
        now = s.conn.execute('SELECT now() AS now, current_setting(%s) AS ro', ('transaction_read_only',)).fetchone()
        emit('check', at=datetime.now(UTC), script_sha256=sha256(b64decode(os.environ['C76_PROBE'])).hexdigest(), db_now=now['now'], read_only=now['ro'], schema=config.schema)
        rows = s.conn.execute(sql.SQL("""SELECT g.id, g.created_at, g.completed_at, g.expires_at, g.sources,
                (SELECT count(*) FROM {c} WHERE generation_id=g.id) AS rows,
                (SELECT count(*) FROM {c} WHERE generation_id=g.id AND market='TW') AS tw,
                (SELECT count(*) FROM {c} WHERE generation_id=g.id AND market='US') AS us
            FROM {g} g ORDER BY g.completed_at DESC, g.id DESC""").format(g=g, c=c)).fetchall()
        for r in rows:
            emit('generation', id=r['id'], created_at=r['created_at'], completed_at=r['completed_at'],
                 expires_at=r['expires_at'], rows=r['rows'], tw=r['tw'], us=r['us'],
                 sources=[{k: x[k] for k in ('name', 'fetched_at', 'row_count', 'payload_hash', 'tls_relaxed')}
                          for x in r['sources']])
        # The generation load_instrument_catalog would pick right now (storage.py).
        current = s.conn.execute(sql.SQL('SELECT id FROM {} WHERE completed_at<=now() AND expires_at>=now() '
                                         'ORDER BY completed_at DESC LIMIT 1').format(g)).fetchone()
        emit('current', id=current['id'] if current else None, generations=len(rows))

"""C7-6 wrap-up: confirm the purge left nothing of the five rounds, read only.

Carried base64-encoded in C76_PROBE for one execution of the c76-source-probe Job, like
docs/c76-catalog-check.py. One READ ONLY transaction, SELECTs only. The ids are the
combined manifest the administrator purged (output/c76/purge-manifest.json); counting
them per table with cloud_db's own run_scope checks exactly what purge deleted.

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
from uuid import UUID

from psycopg import sql

from stock_quote_fetcher.cloud_db import RUN_TABLES, RUNTIME_TABLES, run_scope
from stock_quote_fetcher.config import load_database_config
from stock_quote_fetcher.storage import Storage

RUNS = [UUID(x) for x in (
    '676eba17-90b2-4301-9dd6-dfc0114d167b', '717bace7-1c44-4874-b012-44194265a7b0', '9f3a7ef5-6c40-4510-b5ba-69fbe5d3d8b1',
    '5562c234-6c5a-40ec-9a45-3adf191c9cd6', '7ddc58fa-39fb-4e07-9858-e8b38a8990dc', 'a05864af-3631-4cd3-b587-200f7772549d',
    '6443d6c2-7c1b-4e1d-8f36-c05bec3b49e6', '7010f9ff-b832-41db-bd0a-585b7ffd0d3a', 'ba7ca41d-4952-492b-8be0-09cc359dddea',
    '5b7256be-9a86-4a43-8ae6-6ce85f71ffe6', '741c85e1-301c-415c-97eb-a6cd2ef9c2f4', '9827b751-21e6-44a5-9974-0dc71dce2060',
    'cda3fe06-76a4-46a4-a6e9-6db30c8c0a65', 'dd4c883f-109a-443c-964e-27cb3018f4d0', 'e2796bcf-eec2-483b-b1dd-07c05e6907ee',
    'e6d0122f-a906-4d11-89d4-a14328cd9390', 'eb32caa4-c495-4dad-88eb-fa6faa78f648')]
JOBS = ['c439a9f2-cb2b-488d-9a03-e55f1b905f34', '3213a160-796b-4920-b71a-5126162f70f9', '0015ab84-cc5b-4029-82d5-c356f1656a48',
        'aa60a176-7045-4294-a93b-c051a210ef6b', 'b73cf54f-291d-4212-9361-77964821859b']


def emit(kind, **fields):
    sys.stdout.write('C76 ' + json.dumps({'kind': kind, **fields}, ensure_ascii=False, default=str) + '\n')
    sys.stdout.flush()


config = replace(load_database_config(Path('/app/cloud.toml')), schema='dashboard')
with Storage(config) as s:
    with s.transaction(writer=False, readonly=True):
        t = s.table
        now = s.conn.execute('SELECT now() AS now, current_setting(%s) AS ro', ('transaction_read_only',)).fetchone()
        emit('check', at=datetime.now(UTC), script_sha256=sha256(b64decode(os.environ['C76_PROBE'])).hexdigest(),
             db_now=now['now'], read_only=now['ro'], schema=config.schema, runs=len(RUNS), jobs=len(JOBS))
        left = {name: s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE {}').format(t(name), run_scope(t, name)),
                                     (RUNS,)).fetchone()['n'] for name in RUN_TABLES}
        left['refresh_jobs'] = s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE id=ANY(%s)').format(t('refresh_jobs')),
                                              (JOBS,)).fetchone()['n']
        emit('purged_ids_remaining', **left)
        # Whole-table counts: what is left in the schema at all, for the evidence.
        emit('table_rows', **{name: s.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(t(name))).fetchone()['n']
                              for name in RUNTIME_TABLES})
        document = s.conn.execute(sql.SQL('SELECT document FROM {} WHERE id=1').format(t('portfolio'))).fetchone()['document']
        emit('portfolio', revision=document.get('revision'), rows=len(document.get('rows') or []),
             instruments=len(document.get('instruments') or {}), fx=document.get('fx'))

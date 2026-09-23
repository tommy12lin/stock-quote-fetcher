"""C7-6 source measurement, run inside the real web image as a Cloud Run Job.

Not part of the service. The Job replaces the image's command with

    python -c "exec(__import__('base64').b64decode(__import__('os').environ['C76_PROBE']))"

and carries this file base64-encoded in C76_PROBE, so what runs is the exact image C6-2
will deploy, rebuilt for nothing. It calls Dashboard.refresh() in-process: the real
run_job path (staleness order, batches, Supabase writes, retries, cooldowns) without
the HTTP layer, which C3-1's signature check would otherwise stand in front of.

C76_MODE selects one round of docs/cloud-phase-1-plan.md C7-6:
  catalog  R1: refresh the official listing only.
  refresh  R2-R5: save C76_TICKERS ("fixed" or "wide:N") as the portfolio, refresh once.
  reset    after the last round: save an empty portfolio at C76_EXPECT_REVISION.

Every output line is "C76 " plus one JSON object, so Cloud Logging can be filtered and
the lines reassembled into evidence. catalog and refresh always print one "manifest"
line: the input to `python -m stock_quote_fetcher.cloud_db purge`.
"""
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import monotonic

from psycopg import sql

from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.storage import Storage
from stock_quote_fetcher.web_input import WebError

# Step 9's fixed list (docs/step-9-evidence.md section 3): listed and OTC stocks and
# ETFs, US stocks including a share class, US ETFs; 006201 doubles as the thin-volume case.
FIXED = ('2330', '2317', '0050', '6488', '3529', '006201', 'AAPL', 'MSFT', 'BRK.B', 'VOO', 'QQQ')


def emit(out, kind, **fields):
    out.write('C76 ' + json.dumps({'kind': kind, **fields}, ensure_ascii=False, default=str) + '\n')
    out.flush()


def select_wide(entries, count):
    """count stocks and ETFs, half per market, spread by hash rather than by alphabet.

    Alphabetical slices cluster (Taiwan codes starting 00 are all ETFs); a hash of the
    stable id spreads the pick yet repeats exactly for the same catalog generation.
    """
    pool = [e for e in entries if e.asset_type in ('stock', 'etf')]
    picked = []
    for market, share in (('TW', count // 2), ('US', count - count // 2)):
        ranked = sorted((e for e in pool if e.market.value == market),
                        key=lambda e: sha256(e.instrument_id.encode()).hexdigest())
        if len(ranked) < share:
            raise ValueError(f'官方清單的 {market} 標的不足 {share} 檔。')
        picked += [e.ticker for e in ranked[:share]]
    return tuple(picked)


def tickers_for(spec, entries):
    if spec == 'fixed':
        return FIXED
    count = spec.removeprefix('wide:')
    if not spec.startswith('wide:') or not count.isdigit() or not 2 <= int(count) <= 500:
        raise ValueError('C76_TICKERS 必須是 fixed 或 wide:N（N 介於 2 與 500）。')
    return select_wide(entries, int(count))


def run_ids(service):
    with Storage(service.db) as s:
        return {r['id'] for r in s.conn.execute(sql.SQL('SELECT id FROM {}').format(s.table('runs')))}


def refreshed(service, out, **options):
    """One refresh, bracketed so the runs it wrote are known by id.

    run_job keeps its run ids to itself, so they are recovered as the difference of two
    snapshots. Valid only while nothing else writes runs, which holds before C6-2: no
    service is deployed, and the collector lock serialises refreshes anyway.
    """
    before = run_ids(service)
    started_at = datetime.now(UTC)
    clock = monotonic()
    job = service.refresh(**options)
    elapsed = monotonic() - clock
    runs = sorted(run_ids(service) - before)
    # A job owned by another instance was not started here; it is not ours to purge.
    mine = job.get('owner') == service.instance
    emit(out, 'manifest', runs=[str(r) for r in runs], refresh_jobs=[job['job_id']] if mine else [])
    emit(out, 'job', job_id=job['job_id'], owned=mine, status=job['status'], message=job['message'],
         refresh_started_at=started_at, elapsed_seconds=round(elapsed, 3))
    return runs


def report(service, runs, out):
    with Storage(service.db) as s:
        t = s.table
        for row in s.conn.execute(sql.SQL("""SELECT r.id AS run_id, r.started_at, r.ended_at, r.status,
                (SELECT count(*) FROM {h} h WHERE h.run_id=r.id) AS tickers FROM {r} r
                WHERE r.id=ANY(%s) ORDER BY r.started_at""").format(r=t('runs'), h=t('holdings')), (runs,)):
            emit(out, 'batch', **row)
        # Flags twice: as stored when fetched, and as the valuation of that cycle saw them.
        for row in s.conn.execute(sql.SQL("""SELECT a.run_id, c.market, a.ticker, a.provider, a.attempt_number,
                a.status, a.error_code, a.elapsed_ms, a.started_at, a.completed_at,
                a.response_evidence->'adapter' AS adapter, q.price, q.price_kind, q.quote_time, q.received_at,
                q.trading_date, q.session, q.declared_delay_seconds, q.quality_flags, v.quality_flags AS valuation_flags
                FROM {a} a JOIN {c} c ON c.id=a.cycle_id LEFT JOIN {q} q ON q.attempt_id=a.id
                LEFT JOIN {v} v ON v.quote_id=q.id AND v.run_id=a.run_id
                WHERE a.run_id=ANY(%s) ORDER BY a.started_at""").format(
                    a=t('fetch_attempts'), c=t('cycles'), q=t('quotes'), v=t('valuations')), (runs,)):
            emit(out, 'attempt', **row)
    # What the page would show now: flags re-assessed at read time (dashboard.py valuation).
    for row in service.valuation()['rows']:
        emit(out, 'view', **row)


def catalog_round(service, out):
    refreshed(service, out, catalog_only=True)
    with Storage(service.db) as s:
        generation, entries = s.load_instrument_catalog()
    emit(out, 'catalog', generation_id=generation['id'], completed_at=generation['completed_at'],
         instruments=len(entries), by_market={m: sum(e.market.value == m for e in entries) for m in ('TW', 'US')})


def refresh_round(service, spec, out):
    tickers = tickers_for(spec, service.catalog())
    current = service.get()
    # D5's fake holdings: only the tickers matter, so quantity and cost are placeholders.
    saved = service.save({'revision': current['revision'], 'fx': None,
                          'rows': [{'ticker': t, 'quantity': '1', 'buy_price': '1'} for t in tickers]})
    # Printed before refreshing, so reset can run even if the refresh itself is refused.
    emit(out, 'portfolio', revision=saved['revision'], spec=spec, tickers=list(tickers))
    report(service, refreshed(service, out), out)


def reset_round(service, revision, out):
    # Dashboard.save's own revision check: a portfolio saved since the probe gets 409.
    saved = service.save({'revision': revision, 'rows': [], 'fx': None})
    emit(out, 'reset', revision=saved['revision'])


def main(env=os.environ, out=sys.stdout):
    mode = env.get('C76_MODE')
    if mode not in ('catalog', 'refresh', 'reset'):
        emit(out, 'error', message='C76_MODE 必須是 catalog、refresh 或 reset。')
        return 2
    expected = env.get('C76_EXPECT_REVISION', '')
    if mode == 'reset' and not expected.isdigit():
        emit(out, 'error', message='reset 需要 C76_EXPECT_REVISION（最後一場印出的 portfolio revision）。')
        return 2
    # C76_SCHEMA exists for the isolated test database; the Job leaves it unset.
    service = Dashboard(Path(env.get('C76_CONFIG', '/app/cloud.toml')), env.get('C76_SCHEMA', 'dashboard'))
    emit(out, 'start', mode=mode, at=datetime.now(UTC), instance=service.instance,
         deadline_seconds=service.refresh_config.deadline_seconds, max_tickers=service.refresh_config.max_tickers)
    try:
        if mode == 'catalog':
            catalog_round(service, out)
        elif mode == 'refresh':
            refresh_round(service, env.get('C76_TICKERS', 'fixed'), out)
        else:
            reset_round(service, int(expected), out)
    except WebError as exc:
        emit(out, 'error', status=exc.status, **exc.payload)
        return 1
    except ValueError as exc:
        emit(out, 'error', message=str(exc))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

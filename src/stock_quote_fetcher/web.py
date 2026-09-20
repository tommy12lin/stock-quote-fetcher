"""ASGI entry point for the personal dashboard. Static assets are served by the edge, not here."""
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
import json
import os
import re
import secrets
import sys

import anyio
from fastapi import FastAPI, Request
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as RoutingError
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
import uvicorn

from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.storage import Storage, lock_key
from stock_quote_fetcher.web_input import WebError, MAX_UPLOAD, bounded_preview, template_xlsx

# Blocking work (psycopg, quote runs) stays off the event loop; this caps how many
# such calls run at once, replacing the accept-side semaphore of the previous server.
CONCURRENCY = 8
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
# No document is served from this process, so the policy only has to deny everything.
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
           'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
           'Referrer-Policy': 'no-referrer'}
ANY_HOST = '*'
HOST_PATTERN = re.compile(r'^[A-Za-z0-9.\-]+(:\d+)?$')
ORIGIN_PATTERN = re.compile(r'^https?://[A-Za-z0-9.\-]+(:\d+)?$')
# Liveness only, and outside /api so that neither the guard nor C3-1's signature applies.
HEALTH_PATH = '/healthz'
DEFAULT_PORT = 8765


class ConfigError(ValueError):
    """Raised at startup only: a bad allowlist must never become a runtime surprise."""


def allowlist(name, default, pattern, wildcard=False):
    """Reads a comma-separated allowlist from the environment, or keeps the local default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    entries = {item.strip() for item in raw.split(',') if item.strip()}
    if not entries:
        raise ConfigError(f'{name} 不得為空；未設定時才會套用本機預設值。')
    if wildcard and entries == {ANY_HOST}:
        return ANY_HOST
    bad = sorted(entry for entry in entries if not pattern.fullmatch(entry))
    if bad:
        raise ConfigError(f'{name} 的項目格式無效：{", ".join(bad)}')
    return entries


def listen_port(explicit):
    """An explicit --port wins; otherwise the platform's PORT, otherwise the local default."""
    if explicit is not None:
        return explicit
    raw = os.environ.get('PORT')
    if raw is None:
        return DEFAULT_PORT
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ConfigError(f'PORT 必須是 1–65535 的整數，收到：{raw!r}')
    return int(raw)


def access_rules(port):
    """Host and Origin allowlists. Defaults reproduce the loopback-only behaviour."""
    hosts = allowlist('WEB_ALLOWED_HOSTS', {f'localhost:{port}', f'127.0.0.1:{port}'}, HOST_PATTERN, wildcard=True)
    raw = os.environ.get('WEB_ALLOWED_ORIGINS')
    if raw is not None and ANY_HOST in {item.strip() for item in raw.split(',')}:
        raise ConfigError('WEB_ALLOWED_ORIGINS 不接受萬用字元：Origin 檢查是跨站寫入的唯一防線。')
    origins = allowlist('WEB_ALLOWED_ORIGINS', {f'http://localhost:{port}', f'http://127.0.0.1:{port}'}, ORIGIN_PATTERN)
    return hosts, origins


def respond(status, body, content_type='application/json; charset=utf-8'):
    if not isinstance(body, bytes):
        body = json.dumps(body, ensure_ascii=False).encode()
    return Response(body, status_code=status, media_type=content_type, headers=HEADERS)


def first(request, name, default=None):
    """Mirrors parse_qs: a repeated parameter resolves to its first value."""
    values = request.query_params.getlist(name)
    return values[0] if values else default


async def body_bytes(request):
    """Reads the body under the upload cap without trusting Content-Length alone."""
    declared = request.headers.get('content-length')
    size = None
    if declared is not None:
        try:
            size = int(declared)
        except ValueError:
            raise WebError('上傳大小無效。') from None
        if not 0 <= size <= MAX_UPLOAD:
            raise WebError('檔案不得超過 5 MiB。', status=413)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_UPLOAD:
            raise WebError('檔案不得超過 5 MiB。', status=413)
    if size is not None and len(raw) != size:
        raise WebError('上傳未完成。')
    return bytes(raw)


class Guard:
    """Host, Origin and token checks run before routing, as the previous handler did.

    Only the Host header is consulted; X-Forwarded-Host and friends are forgeable by
    anyone who can reach the service, so no proxy header takes part in any decision.
    """

    def __init__(self, app, hosts, origins, token):
        self.app, self.token = app, token
        self.hosts, self.origins = hosts, origins

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        if scope['path'] == HEALTH_PATH:
            # The platform's probe cannot carry a Host of our choosing, an Origin or a token,
            # and this path answers a constant, so no check has anything to protect here.
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        denied = None
        if self.hosts != ANY_HOST and headers.get('host') not in self.hosts:
            denied = WebError('拒絕不合法的 Host。', status=403)
        elif scope['method'] != 'GET' and (headers.get('origin') not in self.origins
                                           or headers.get('x-portfolio-token') != self.token):
            denied = WebError('請從本機儀表板進行操作。', status=403)
        if denied is not None:
            return await respond(denied.status, denied.payload)(scope, receive, send)
        await self.app(scope, receive, send)


class Failsafe:
    """Swallows the exception Starlette re-raises after the 503 body has been sent.

    Only the type and route are recorded: exception text can carry tickers, which are
    holdings data and must not reach the platform's logs.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            if scope['type'] != 'http':
                raise
            print(f"unhandled {type(exc).__name__} at {scope['method']} {scope['path']}", file=sys.stderr, flush=True)


@asynccontextmanager
async def lifespan(app):
    anyio.to_thread.current_default_thread_limiter().total_tokens = CONCURRENCY
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.exception_handler(WebError)
async def rejected(request, exc):
    return respond(exc.status, exc.payload)


@app.exception_handler(json.JSONDecodeError)
@app.exception_handler(UnicodeDecodeError)
async def malformed(request, exc):
    return respond(400, {'message': '請求格式錯誤。'})


@app.exception_handler(RoutingError)
async def unrouted(request, exc):
    # Unknown paths and methods answer alike; neither confirms which routes exist.
    return respond(404, WebError('找不到頁面。', status=404).payload)


@app.exception_handler(Exception)
async def unavailable(request, exc):
    return respond(503, {'message': '服務暫不可用，請確認資料庫及設定後重試；未保存內容仍保留。'})


@app.get(HEALTH_PATH)
async def health(request: Request):
    """Answers from the process alone: no database, no migration, no quote provider."""
    return respond(200, {'status': 'ok'})


@app.get('/api/session')
async def session(request: Request):
    return respond(200, {'token': request.app.state.token})


@app.get('/api/portfolio')
async def portfolio(request: Request):
    return respond(200, await run_in_threadpool(request.app.state.service.get))


@app.get('/api/portfolio/valuation')
async def valuation(request: Request):
    return respond(200, await run_in_threadpool(request.app.state.service.valuation, first(request, 'market', 'ALL')))


@app.get('/api/jobs/{job_id}')
async def job(request: Request, job_id: str):
    return respond(200, await run_in_threadpool(request.app.state.service.job, job_id))


@app.get('/api/templates/holdings.xlsx')
async def template(request: Request):
    return respond(200, await run_in_threadpool(template_xlsx), XLSX)


@app.post('/api/imports/preview')
async def preview(request: Request):
    raw = await body_bytes(request)
    if not (first(request, 'filename') or '').lower().endswith('.xlsx'):
        raise WebError('只接受 .xlsx 檔案。')
    return respond(200, await run_in_threadpool(bounded_preview, raw, first(request, 'sheet')))


@app.put('/api/portfolio')
async def save(request: Request):
    document = json.loads(await body_bytes(request))
    return respond(200, await run_in_threadpool(request.app.state.service.save, document))


@app.post('/api/portfolio/refresh')
async def refresh(request: Request):
    await body_bytes(request)
    return respond(202, await run_in_threadpool(request.app.state.service.refresh))


@app.post('/api/catalog/refresh')
async def refresh_catalog(request: Request):
    await body_bytes(request)
    return respond(202, await run_in_threadpool(request.app.state.service.refresh, True))


def main():
    parser = argparse.ArgumentParser(description='本機持股儀表板')
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--schema', default='dashboard')
    parser.add_argument('--port', type=int, default=None, help=f'未指定時取環境變數 PORT，再無則 {DEFAULT_PORT}')
    parser.add_argument('--container', action='store_true',
                        help='監聽所有介面；本機容器須搭配 loopback published port，代管平台（Cloud Run）則必須指定')
    parser.add_argument('--initialize', action='store_true', help='明確初始化專用 schema 後退出')
    parser.add_argument('--refresh-catalog', action='store_true', help='更新專用 schema 官方清單後退出')
    args = parser.parse_args()
    try:
        port = listen_port(args.port)
        hosts, origins = access_rules(port)
    except ConfigError as exc:
        parser.error(str(exc))
    service = Dashboard(args.config, args.schema)
    if args.initialize:
        service.initialize()
        print('Dashboard schema initialized.')
        return
    if args.refresh_catalog:
        from stock_quote_fetcher.catalog import fetch_all
        with Storage(service.db) as s:
            s.acquire_lock()
            s.save_instrument_catalog(fetch_all(service.catalog_config), max_age_hours=service.catalog_config.max_age_hours)
        print('Dashboard catalog refreshed.')
        return
    # Singleton process lease separate from both collector locks; protects recovery.
    with Storage(service.db) as lease:
        acquired = lease.conn.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (lock_key(args.schema + ':web'),)).fetchone()['acquired']
        if not acquired:
            parser.error('同一 schema 已有儀表板服務。')
        service.recover_jobs()
        app.state.service, app.state.token = service, secrets.token_urlsafe(32)
        host = '0.0.0.0' if args.container else '127.0.0.1'
        print(f'Portfolio dashboard API: listening on {host}:{port}', flush=True)
        print(f'Allowed hosts: {hosts if hosts == ANY_HOST else ", ".join(sorted(hosts))}', flush=True)
        print(f'Allowed origins: {", ".join(sorted(origins))}', flush=True)
        # Access logs would carry query strings, which hold filenames and market filters.
        # proxy_headers=False: X-Forwarded-* reach this service unverified and nothing here needs them.
        uvicorn.run(Failsafe(Guard(app, hosts, origins, app.state.token)), host=host, port=port,
                    access_log=False, server_header=False, proxy_headers=False, log_level='warning')


if __name__ == '__main__':
    main()

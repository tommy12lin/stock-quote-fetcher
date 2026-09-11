"""Dependency-free, loopback-only HTTP entry point for the personal dashboard."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import secrets
from threading import BoundedSemaphore
from urllib.parse import urlsplit, parse_qs

from psycopg import sql
from stock_quote_fetcher.dashboard import Dashboard
from stock_quote_fetcher.storage import Storage, lock_key
from stock_quote_fetcher.web_input import WebError, MAX_UPLOAD, bounded_preview, template_xlsx


class LocalServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        self.slots = BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        self.slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'Portfolio/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Holdings, request bodies and query strings never enter access logs.

    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(body)

    def handle_request(self):
        try:
            allowed = {f'localhost:{self.server.public_port}', f'127.0.0.1:{self.server.public_port}'}
            host = self.headers.get('Host')
            if host not in allowed:
                raise WebError('拒絕不合法的 Host。', status=403)
            if self.command != 'GET':
                if self.headers.get('Origin') not in {f'http://{h}' for h in allowed} or self.headers.get('X-Portfolio-Token') != self.server.token:
                    raise WebError('請從本機儀表板進行操作。', status=403)
            route = urlsplit(self.path)
            query = parse_qs(route.query)
            service = self.server.service
            if self.command == 'GET':
                if route.path == '/api/session':
                    return self.respond(200, {'token': self.server.token})
                if route.path == '/api/portfolio':
                    return self.respond(200, service.get())
                if route.path == '/api/portfolio/valuation':
                    return self.respond(200, service.valuation(query.get('market', ['ALL'])[0]))
                if route.path.startswith('/api/jobs/'):
                    return self.respond(200, service.job(route.path.rsplit('/', 1)[-1]))
                if route.path == '/api/templates/holdings.xlsx':
                    return self.respond(200, template_xlsx(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
                if route.path in static:
                    name, kind = static[route.path]
                    return self.respond(200, (Path(__file__).parent / 'static' / name).read_bytes(), kind + '; charset=utf-8')
            else:
                if self.headers.get('Transfer-Encoding'):
                    raise WebError('不支援分塊上傳。')
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise WebError('上傳大小無效。') from None
                if not 0 <= size <= MAX_UPLOAD:
                    raise WebError('檔案不得超過 5 MiB。', status=413)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise WebError('上傳未完成。')
                if self.command == 'POST' and route.path == '/api/imports/preview':
                    if not query.get('filename', [''])[0].lower().endswith('.xlsx'):
                        raise WebError('只接受 .xlsx 檔案。')
                    return self.respond(200, bounded_preview(raw, query.get('sheet', [None])[0]))
                if self.command == 'PUT' and route.path == '/api/portfolio':
                    return self.respond(200, service.save(json.loads(raw)))
                if self.command == 'POST' and route.path == '/api/portfolio/refresh':
                    return self.respond(202, service.refresh())
                if self.command == 'POST' and route.path == '/api/catalog/refresh':
                    return self.respond(202, service.refresh(catalog_only=True))
            raise WebError('找不到頁面。', status=404)
        except WebError as exc:
            self.respond(exc.status, exc.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.respond(400, {'message': '請求格式錯誤。'})
        except Exception:
            self.respond(503, {'message': '服務暫不可用，請確認資料庫及設定後重試；未保存內容仍保留。'})

    do_GET = do_POST = do_PUT = handle_request


def main():
    parser = argparse.ArgumentParser(description='本機持股儀表板')
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--schema', default='dashboard')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--container', action='store_true', help='容器內監聽；必須搭配 loopback published port')
    parser.add_argument('--initialize', action='store_true', help='明確初始化專用 schema 後退出')
    parser.add_argument('--refresh-catalog', action='store_true', help='更新專用 schema 官方清單後退出')
    args = parser.parse_args()
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
        server = LocalServer(('0.0.0.0' if args.container else '127.0.0.1', args.port), Handler)
        server.service, server.token, server.public_port = service, secrets.token_urlsafe(32), args.port
        print(f'Portfolio dashboard: http://localhost:{args.port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()

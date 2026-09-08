"""CLI contract; functional commands are implemented in later plan steps."""

import argparse
from importlib.metadata import version
from pathlib import Path
import sys

from stock_quote_fetcher.input import InputValidationError, load_holdings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-poc",
        description="台美股報價 POC：CSV 驗證、標的映射與單次報價。",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('stock-quote-fetcher')}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="離線驗證 CSV")
    validate.add_argument("--input", type=Path, required=True)
    for name, help_text in (("db-check", "驗證專用帳號與 schema"), ("migrate", "套用資料庫 migration（先停止 monitor）")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--config", type=Path, required=True)
        if name == "db-check":
            command.add_argument("--connection-only", action="store_true", help="只檢查連線與 migration 所需 schema 權限")
    health = commands.add_parser("healthcheck", help="檢查 monitor 的資料庫連線與心跳")
    health.add_argument("--config", type=Path, required=True)
    health.add_argument("--max-heartbeat-age-seconds", type=int, default=120)
    refresh = commands.add_parser('instruments-refresh', help='更新官方標的清單')
    refresh.add_argument('--config', type=Path, required=True)
    resolve = commands.add_parser('resolve', help='驗證標的並顯示來源代碼')
    resolve.add_argument('--input', type=Path, required=True)
    resolve.add_argument('--config', type=Path, required=True)
    for name, help_text in (
        ("quote", "單次報價並保存估值與來源證據"),
        ("monitor", "持續觀測（步驟 6 待實作）"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "monitor":
            command.add_argument("--campaign-id", help="明確續跑指定 campaign UUID；省略時自動續接相同設定")
    report = commands.add_parser("report", help="產生報告（步驟 8 待實作）")
    report.add_argument("--run-id", required=True)
    report.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == 'monitor':
        from threading import Event
        from stock_quote_fetcher.config import ConfigurationError
        from stock_quote_fetcher.monitor import execute, stop_signals
        from stock_quote_fetcher.storage import StorageError
        event = Event()
        try:
            with stop_signals(event):
                code, directory, document = execute(
                    args.input, args.config, args.output,
                    campaign_id=args.campaign_id, stop_event=event)
            state = '安全停止，可續跑' if document['status'] == 'interrupted' else '觀測完成'
            print(f"campaign-id {document['campaign_id']}；run-id {document['run_id']}；{state}；輸出：{directory}")
            return code
        except (ConfigurationError, InputValidationError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except (OSError, UnicodeError):
            print('monitor 輸出寫入失敗；資料庫可能已有本次紀錄，請核對路徑與權限。', file=sys.stderr)
            return 1
        except StorageError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == 'quote':
        from stock_quote_fetcher.config import ConfigurationError
        from stock_quote_fetcher.storage import StorageError
        from stock_quote_fetcher.quoting import execute
        try:
            code, directory, document = execute(args.input,args.config,args.output)
            for cycle in document['cycles']:
                for row in cycle['holdings']:
                    print(f"{row['ticker']}: {row['price'] or '缺價'} {row['currency']}；市值 {row['market_value_display'] or '無法估值'}；{','.join(row['quality_flags'])}")
                for summary in cycle['summaries']:
                    label = '總額' if summary['total'] is not None else '已知部分小計'
                    print(f"{summary['currency']} {label} {summary['known_subtotal_display']}（{summary['completeness']}）")
            failed = sum(event['status'] != 'success' for event in document['attempts'])
            if failed:
                print(f'來源嘗試失敗／未執行 {failed} 次；詳見 summary.json。',file=sys.stderr)
            print(f"run-id {document['run_id']}；輸出：{directory}")
            return code
        except (ConfigurationError,InputValidationError) as exc:
            print(str(exc),file=sys.stderr)
            return 2
        except (OSError,UnicodeError):
            print('執行或輸出寫入失敗；資料库可能已有本次紀錄，請核對路徑與權限。',file=sys.stderr)
            return 1
        except StorageError as exc:
            print(str(exc),file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print('報價已中止；保留已提交的執行紀錄。',file=sys.stderr)
            return 1
    if args.command in {"db-check", "migrate", "healthcheck"}:
        from stock_quote_fetcher.config import ConfigurationError, load_database_config
        from stock_quote_fetcher.storage import Storage, StorageError
        try:
            config = load_database_config(args.config)
            with Storage(config) as storage:
                if args.command == "healthcheck":
                    storage.check_schema()
                    info = storage.check_monitor_health(max_age_seconds=args.max_heartbeat_age_seconds)
                    print(f"monitor 正常：run-id {info['run_id']}；心跳年齡 {info['age_seconds']:.1f} 秒。")
                    return 0
                info = storage.check_permissions(migration=True)
                if args.command == "migrate":
                    applied = storage.migrate()
                    storage.check_schema()
                    print(f"Migration 成功：套用 {len(applied)} 個版本。")
                else:
                    if not args.connection_only:
                        storage.check_schema()
                    print(f"資料庫檢查成功：PostgreSQL {info['server_version']}；專用帳號權限符合。")
            return 0
        except ConfigurationError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except StorageError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command in {'instruments-refresh','resolve'}:
        from stock_quote_fetcher.catalog import fetch_all
        from stock_quote_fetcher.config import ConfigurationError, load_database_config, load_instrument_catalog_config
        from stock_quote_fetcher.instruments import CatalogError, resolve_holdings
        from stock_quote_fetcher.storage import Storage, StorageError
        try:
            database = load_database_config(args.config)
            catalog_config = load_instrument_catalog_config(args.config)
            if args.command == 'instruments-refresh':
                with Storage(database) as storage:
                    storage.acquire_lock()
                    storage.check_schema()
                    fetched = fetch_all(catalog_config)
                    generation = storage.save_instrument_catalog(fetched,max_age_hours=catalog_config.max_age_hours)
                total = sum(len(item.entries) for item in fetched)
                print(f'標的清單更新成功：{total} 筆；generation {generation}。')
                return 0
            holdings = load_holdings(args.input)
            with Storage(database) as storage:
                generation, entries = storage.load_instrument_catalog()
            resolved, issues = resolve_holdings(holdings,entries)
            for holding in holdings:
                instrument = resolved.get(holding.ticker)
                if instrument:
                    print(f'{holding.ticker}: {instrument.exchange} {instrument.asset_type} {instrument.provider_symbols["yahoo"]}')
            for issue in issues:
                print(f'{issue.ticker}: {issue.reason}',file=sys.stderr)
            return 0 if not issues else 3
        except (ConfigurationError, InputValidationError) as exc:
            if isinstance(exc, InputValidationError):
                for issue in exc.issues:
                    print(f'第 {issue.line} 行：{issue.message}',file=sys.stderr)
            else:
                print(str(exc),file=sys.stderr)
            return 2
        except OSError as exc:
            print(f'無法讀取輸入檔案：{exc.strerror or type(exc).__name__}',file=sys.stderr)
            return 2
        except (CatalogError, StorageError) as exc:
            print(str(exc),file=sys.stderr)
            return 1
    if args.command == "validate":
        try:
            holdings = load_holdings(args.input)
        except InputValidationError as exc:
            for issue in exc.issues:
                print(f"第 {issue.line} 行：{issue.message}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"無法讀取輸入檔案：{exc.strerror or type(exc).__name__}", file=sys.stderr)
            return 2
        print(f"驗證成功：{len(holdings)} 筆持股（僅格式驗證，未確認標的存在性）。")
        return 0
    print(f"{args.command} 尚未實作；目前僅提供 CLI 骨架。", file=sys.stderr)
    return 1

"""Database configuration. Secrets are environment-only and never snapshotted."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import tomllib


class ConfigurationError(ValueError):
    pass


# libpq's prefer and allow are deliberately absent: they encrypt when the server offers
# TLS and fall back to plaintext when it does not, without telling anyone (C5-3).
SSLMODES = ("disable", "require", "verify-ca", "verify-full")


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "postgres"
    port: int = 5432
    name: str = "stock_quote_fetcher"
    schema: str = "app"
    user: str = "stock_quote_app"
    password: str = field(default="", repr=False, compare=False)
    connect_timeout: int = 10
    statement_timeout_ms: int = 10000
    lock_timeout_ms: int = 3000
    # Secure by default: a deployment that says nothing gets a verified TLS connection,
    # and a local database without TLS has to say so (DB_SSLMODE=disable).
    sslmode: str = "verify-full"
    sslrootcert: str = "system"

    def __post_init__(self):
        if not isinstance(self.schema, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", self.schema) or self.schema.startswith("pg_") or self.schema in {"public", "information_schema"}:
            raise ConfigurationError("database.schema 必須是專案專用的小寫 SQL 識別碼。")
        for name, upper in (("port", 65535), ("connect_timeout", 120), ("statement_timeout_ms", 300000), ("lock_timeout_ms", 300000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                raise ConfigurationError(f"database.{name} 超出允許範圍。")
        if any(not isinstance(v, str) or not v or "\x00" in v for v in (self.host, self.name, self.user, self.password)):
            raise ConfigurationError("資料庫連線設定不完整；請由 DB_PASSWORD 注入密碼。")
        if self.sslmode not in SSLMODES:
            raise ConfigurationError(f"database.sslmode 僅接受 {'／'.join(SSLMODES)}；prefer 與 allow 會在對方不提供 TLS 時靜默改送明文。")
        if self.sslmode.startswith("verify") and (not isinstance(self.sslrootcert, str) or not self.sslrootcert):
            raise ConfigurationError("database.sslrootcert 不可為空；verify-ca／verify-full 需要信任根，system 表示作業系統信任庫。")


def runtime_image_id(environ=None) -> str:
    """Record the running image. APP_IMAGE_ID is injected per deployment; the build bakes
    APP_BASE_IMAGE so a run always names at least its exact base image."""
    env = os.environ if environ is None else environ
    explicit = (env.get("APP_IMAGE_ID") or "").strip()
    if explicit:
        return explicit[:200]
    base = (env.get("APP_BASE_IMAGE") or "").strip()
    return f"base:{base[:200]}" if base else "runtime-unspecified"


def _load_document(path: Path) -> dict:
    try:
        with path.open("rb") as source:
            document = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError):
        raise ConfigurationError("無法讀取設定檔或 TOML 格式錯誤。") from None
    if not isinstance(document, dict):
        raise ConfigurationError("設定檔根節點必須是 TOML table。")
    return document


def load_database_config(path: Path, environ=None) -> DatabaseConfig:
    env = os.environ if environ is None else environ
    document = _load_document(path)
    raw = document.get("database", {})
    allowed = {"host", "port", "name", "schema", "user", "connect_timeout", "statement_timeout_ms", "lock_timeout_ms",
               "sslmode", "sslrootcert"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ConfigurationError("database 含不支援的欄位；密碼只能透過環境注入。")
    values = dict(raw)
    for key in ("host", "port", "name", "schema", "user", "sslmode", "sslrootcert"):
        if f"DB_{key.upper()}" in env:
            values[key] = env[f"DB_{key.upper()}"]
    if isinstance(values.get("port"), str):
        try:
            values["port"] = int(values["port"])
        except ValueError:
            raise ConfigurationError("DB_PORT 必須是整數。") from None
    values["password"] = env.get("DB_PASSWORD", "")
    return DatabaseConfig(**values)


@dataclass(frozen=True)
class InstrumentCatalogConfig:
    max_age_hours: int = 24
    operation_timeout_seconds: int = 30
    company_ca_file: str = ''
    relaxed_sources: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.max_age_hours) is not int or not 1 <= self.max_age_hours <= 168:
            raise ConfigurationError('instruments.max_age_hours 必須介於 1 與 168。')
        if type(self.operation_timeout_seconds) is not int or not 1 <= self.operation_timeout_seconds <= 120:
            raise ConfigurationError('instruments.operation_timeout_seconds 必須介於 1 與 120。')
        allowed = {'twse_companies','twse_funds','tpex_isin','nasdaq_listed','nasdaq_other'}
        if not isinstance(self.relaxed_sources, tuple) or set(self.relaxed_sources) - allowed:
            raise ConfigurationError('tls.relaxed_sources 含未知的標的清單來源。')
        if not isinstance(self.company_ca_file, str):
            raise ConfigurationError('tls.company_ca_file 必須是路徑字串。')
        if self.relaxed_sources and not self.company_ca_file:
            raise ConfigurationError('啟用 relaxed_sources 時必須提供 company_ca_file。')


def load_instrument_catalog_config(path: Path) -> InstrumentCatalogConfig:
    document = _load_document(path)
    raw = document.get('instruments', {})
    tls = document.get('tls', {})
    if not isinstance(raw, dict) or set(raw) - {'max_age_hours','operation_timeout_seconds'}:
        raise ConfigurationError('instruments 含不支援的欄位。')
    if not isinstance(tls, dict) or set(tls) - {'company_ca_file','relaxed_sources','relaxed_providers'}:
        raise ConfigurationError('tls 含不支援的欄位。')
    relaxed = tls.get('relaxed_sources', [])
    if not isinstance(relaxed, list) or not all(isinstance(item, str) for item in relaxed):
        raise ConfigurationError('tls.relaxed_sources 必須是字串陣列。')
    return InstrumentCatalogConfig(**raw, company_ca_file=tls.get('company_ca_file',''), relaxed_sources=tuple(relaxed))


@dataclass(frozen=True)
class QuoteConfig:
    valuation: str = 'yahoo'
    comparison: tuple[str, ...] = ()
    operation_timeout_seconds: int = 10
    cycle_budget_seconds: int = 50
    max_retries: int = 2
    poll_interval_seconds: int = 60
    campaign_duration_days: int = 7
    post_close_observation_minutes: int = 30
    heartbeat_interval_seconds: int = 30
    company_ca_file: str = ''
    relaxed_providers: tuple[str, ...] = ()

    def __post_init__(self):
        if self.valuation != 'yahoo':
            raise ConfigurationError('目前估值來源僅支援 yahoo；Finnhub 為獨立比較來源。')
        if (not isinstance(self.comparison, tuple) or any(x not in {'finnhub','twse','tpex'} for x in self.comparison)
                or len(set(self.comparison)) != len(self.comparison)):
            raise ConfigurationError('providers.comparison 必須是 finnhub／twse／tpex 的不重複陣列。')
        for name, lower, upper in (('operation_timeout_seconds',1,120),('cycle_budget_seconds',1,300),
                                   ('max_retries',0,2),('poll_interval_seconds',60,3600),
                                   ('campaign_duration_days',1,31),
                                   ('post_close_observation_minutes',1,120),
                                   ('heartbeat_interval_seconds',5,300)):
            if type(getattr(self,name)) is not int or not lower <= getattr(self,name) <= upper:
                raise ConfigurationError(f'{name} 超出允許範圍。')
        if (not isinstance(self.company_ca_file,str) or not isinstance(self.relaxed_providers,tuple)
                or any(x not in {'finnhub','twse','tpex'} for x in self.relaxed_providers)
                or (self.relaxed_providers and not self.company_ca_file)):
            raise ConfigurationError('tls.relaxed_providers 僅支援 finnhub／twse／tpex 且必須指定公司 CA。')


def load_quote_config(path: Path) -> QuoteConfig:
    doc = _load_document(path)
    providers, scheduler, tls = (doc.get(key,{}) for key in ('providers','scheduler','tls'))
    for raw, allowed in ((providers, {'valuation','comparison'}),
                         (scheduler, {'operation_timeout_seconds','cycle_budget_seconds','max_retries','poll_interval_seconds',
                                      'campaign_duration_days','post_close_observation_minutes','heartbeat_interval_seconds'} | REFRESH_KEYS),
                         (tls, {'company_ca_file','relaxed_sources','relaxed_providers'})):
        if not isinstance(raw,dict) or set(raw) - allowed:
            raise ConfigurationError('報價設定包含不支援的欄位；秘密只能透過環境注入。')
    for raw, key in ((providers,'comparison'),(tls,'relaxed_providers')):
        if key in raw and (not isinstance(raw[key],list) or not all(isinstance(x,str) for x in raw[key])):
            raise ConfigurationError(f'{key} 必須是字串陣列。')
    return QuoteConfig(valuation=providers.get('valuation','yahoo'), comparison=tuple(providers.get('comparison',[])),
                       **{key:value for key,value in scheduler.items() if key not in REFRESH_KEYS},
                       company_ca_file=tls.get('company_ca_file',''),
                       relaxed_providers=tuple(tls.get('relaxed_providers',[])))


REFRESH_KEYS = frozenset({'refresh_deadline_seconds', 'refresh_max_tickers'})


@dataclass(frozen=True)
class RefreshConfig:
    """D3 runs a refresh inside the request, so it needs a wall-clock limit of its own.

    These live in [scheduler] but stay out of QuoteConfig: they bound the HTTP request,
    not a quote cycle, and adding them to QuoteConfig would change the configuration
    snapshot digest that campaign matching depends on (storage.configuration_snapshot).

    Both defaults are provisional. deadline_seconds reuses the per-batch budget the
    dashboard already spent (300s) as a whole-refresh limit, which is strictly tighter
    than the previous behaviour of no total limit at all; it is not a claim about the
    edge timeout. max_tickers defaults to 0 (bounded by the deadline alone). C7-2 and
    C7-6 measure the real values and C6-2 writes them into deploy/cloud.toml before the
    service is deployed. D3 forbids writing a guessed number here.
    """
    deadline_seconds: int = 300
    max_tickers: int = 0

    def __post_init__(self):
        for name, lower, upper in (('deadline_seconds',1,3600), ('max_tickers',0,500)):
            if type(getattr(self,name)) is not int or not lower <= getattr(self,name) <= upper:
                raise ConfigurationError(f'refresh_{name} 超出允許範圍。')


def load_refresh_config(path: Path) -> RefreshConfig:
    scheduler = _load_document(path).get('scheduler', {})
    if not isinstance(scheduler, dict):
        raise ConfigurationError('報價設定包含不支援的欄位；秘密只能透過環境注入。')
    return RefreshConfig(**{key.removeprefix('refresh_'): value
                            for key, value in scheduler.items() if key in REFRESH_KEYS})

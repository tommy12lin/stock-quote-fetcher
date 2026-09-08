"""Bounded HTTPS retrieval of official instrument catalogs."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import ssl

import httpx

from stock_quote_fetcher.config import InstrumentCatalogConfig
from stock_quote_fetcher.instruments import (
    CatalogError, CatalogInstrument, parse_nasdaq_listed, parse_nasdaq_other,
    parse_tpex_isin, parse_twse_companies, parse_twse_funds,
)


MAX_CATALOG_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    parser: object
    content_types: tuple[str, ...]


SOURCES = (
    SourceSpec('twse_companies','https://openapi.twse.com.tw/v1/opendata/t187ap03_L',parse_twse_companies,('application/json',)),
    SourceSpec('twse_funds','https://openapi.twse.com.tw/v1/opendata/t187ap47_L',parse_twse_funds,('application/json',)),
    SourceSpec('tpex_isin','https://isin.twse.com.tw/isin/C_public.jsp?strMode=4',parse_tpex_isin,('text/html',)),
    SourceSpec('nasdaq_listed','https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',parse_nasdaq_listed,('text/plain',)),
    SourceSpec('nasdaq_other','https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt',parse_nasdaq_other,('text/plain',)),
)


@dataclass(frozen=True)
class FetchedCatalog:
    source: str
    fetched_at: datetime
    payload_hash: str
    byte_count: int
    entries: tuple[CatalogInstrument, ...]
    tls_relaxed: bool


def ssl_context(config: InstrumentCatalogConfig, source: str) -> ssl.SSLContext:
    relaxed = source in config.relaxed_sources
    context = ssl.create_default_context()
    if relaxed:
        try:
            context.load_verify_locations(cafile=config.company_ca_file)
        except (OSError, ssl.SSLError):
            raise CatalogError('Unable to load the configured company CA file.') from None
        strict = getattr(ssl, 'VERIFY_X509_STRICT', 0)
        context.verify_flags &= ~strict
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise CatalogError('TLS certificate-chain and hostname verification must remain enabled.')
    return context


def fetch_source(spec: SourceSpec, config: InstrumentCatalogConfig) -> FetchedCatalog:
    context = ssl_context(config, spec.name)
    try:
        with httpx.Client(verify=context, timeout=config.operation_timeout_seconds,
                          follow_redirects=False, trust_env=True) as client:
            with client.stream('GET', spec.url, headers={'Accept': ', '.join(spec.content_types)}) as response:
                response.raise_for_status()
                content_type = response.headers.get('content-type','').split(';',1)[0].strip().lower()
                if content_type not in spec.content_types:
                    raise CatalogError(f'{spec.name} returned unexpected content type.')
                declared = response.headers.get('content-length')
                if declared and declared.isdigit() and int(declared) > MAX_CATALOG_BYTES:
                    raise CatalogError(f'{spec.name} response is too large.')
                parts, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_CATALOG_BYTES:
                        raise CatalogError(f'{spec.name} response is too large.')
                    parts.append(chunk)
        payload = b''.join(parts)
        entries = spec.parser(payload)
    except CatalogError:
        raise
    except (httpx.HTTPError, OSError, ssl.SSLError):
        raise CatalogError(f'{spec.name} official catalog fetch failed.') from None
    return FetchedCatalog(spec.name, datetime.now(UTC), sha256(payload).hexdigest(),
                          len(payload), entries, spec.name in config.relaxed_sources)


def fetch_all(config: InstrumentCatalogConfig) -> tuple[FetchedCatalog, ...]:
    # All sources must parse before the caller replaces the current database generation.
    return tuple(fetch_source(spec, config) for spec in SOURCES)

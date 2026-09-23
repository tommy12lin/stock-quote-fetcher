from datetime import UTC, datetime
import ssl

import httpx
import pytest

from stock_quote_fetcher.catalog import MAX_CATALOG_BYTES, SourceSpec, fetch_source, ssl_context
from stock_quote_fetcher.config import InstrumentCatalogConfig
from stock_quote_fetcher.instruments import CatalogError, CatalogInstrument


def one(payload):
    assert payload == b'payload'
    return (CatalogInstrument('id','AAPL','US','USD','NASDAQ','stock','Apple',{'yahoo':'AAPL'}),)


def test_ssl_context_never_disables_verification():
    normal = ssl_context(InstrumentCatalogConfig(),'nasdaq_listed')
    assert normal.verify_mode == ssl.CERT_REQUIRED and normal.check_hostname


def test_relaxed_context_only_removes_strict_flag(tmp_path,monkeypatch):
    # Use platform defaults while checking the flag behavior; cafile loading is covered by ssl itself.
    class FakeContext:
        verify_mode = ssl.CERT_REQUIRED
        check_hostname = True
        verify_flags = getattr(ssl,'VERIFY_X509_STRICT',0)
        def load_verify_locations(self, *, cafile):
            assert cafile == 'company.pem'
    monkeypatch.setattr(ssl,'create_default_context',lambda: FakeContext())
    config = InstrumentCatalogConfig(company_ca_file='company.pem',relaxed_sources=('twse_companies',))
    context = ssl_context(config,'twse_companies')
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert not (context.verify_flags & getattr(ssl,'VERIFY_X509_STRICT',0))


@pytest.mark.parametrize('status,content_type,body,error',[
    (500,'text/plain',b'payload','fetch failed'),
    (200,'text/html',b'payload','content type'),
    (200,'text/plain',b'x'*(MAX_CATALOG_BYTES+1),'too large'),
])
def test_fetch_rejects_http_content_type_and_size(monkeypatch,status,content_type,body,error):
    transport = httpx.MockTransport(lambda request: httpx.Response(status,headers={'content-type':content_type},content=body))
    real = httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs: real(transport=transport))
    spec = SourceSpec('nasdaq_listed','https://official.example/list.txt',one,('text/plain',))
    with pytest.raises(CatalogError,match=error):
        fetch_source(spec,InstrumentCatalogConfig())


def test_fetch_hashes_and_parses(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200,headers={'content-type':'text/plain'},content=b'payload'))
    real = httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs: real(transport=transport))
    result = fetch_source(SourceSpec('nasdaq_listed','https://official.example/list.txt',one,('text/plain',)),InstrumentCatalogConfig())
    assert result.byte_count == 7 and len(result.payload_hash) == 64 and result.entries[0].ticker == 'AAPL'


def test_relaxed_source_requires_ca_and_known_name():
    from stock_quote_fetcher.config import ConfigurationError
    with pytest.raises(ConfigurationError):
        InstrumentCatalogConfig(relaxed_sources=('twse_companies',))
    with pytest.raises(ConfigurationError):
        InstrumentCatalogConfig(company_ca_file='x.pem',relaxed_sources=('unknown',))


def test_refresh_in_request_must_be_a_real_boolean(tmp_path):
    from stock_quote_fetcher.config import ConfigurationError, load_instrument_catalog_config
    # "false" is truthy; accepting it would silently keep the in-request refresh on.
    for value in ('false', 0, None):
        with pytest.raises(ConfigurationError):
            InstrumentCatalogConfig(refresh_in_request=value)
    path = tmp_path / 'c.toml'
    path.write_text('[instruments]\nrefresh_in_request = false\n', encoding='utf-8')
    assert load_instrument_catalog_config(path).refresh_in_request is False
    assert InstrumentCatalogConfig().refresh_in_request is True  # local behaviour unchanged

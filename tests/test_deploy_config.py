"""The cloud configuration ships inside the image, so it is verified like code (C2-5, C2-7)."""
from importlib.resources import files
from pathlib import Path
import tomllib

import pytest

from stock_quote_fetcher.config import (ConfigurationError, load_database_config,
                                        load_instrument_catalog_config, load_quote_config)

CLOUD = Path(__file__).resolve().parents[1] / 'deploy' / 'cloud.toml'


@pytest.fixture(scope='module')
def document():
    with CLOUD.open('rb') as source:
        return tomllib.load(source)


def test_every_loader_accepts_the_file(monkeypatch):
    # A rejected field raises ConfigurationError, which in the image means a crash loop.
    monkeypatch.setenv('DB_PASSWORD', 'injected-at-runtime')
    assert load_database_config(CLOUD).schema == 'app'
    assert load_quote_config(CLOUD).valuation == 'yahoo'
    assert load_instrument_catalog_config(CLOUD).max_age_hours == 168


def test_the_file_alone_cannot_produce_a_connection(monkeypatch):
    # Fails closed: without DB_PASSWORD the configuration is incomplete, so a deployment
    # that forgets the secret stops at startup instead of reaching for an empty password.
    monkeypatch.delenv('DB_PASSWORD', raising=False)
    with pytest.raises(ConfigurationError):
        load_database_config(CLOUD)


def test_no_company_tls_settings_leak_into_the_cloud(document):
    # [tls] carries the company CA path and relaxed providers; the cloud must have neither.
    assert 'tls' not in document
    assert load_quote_config(CLOUD).company_ca_file == ''
    assert load_quote_config(CLOUD).relaxed_providers == ()
    assert load_instrument_catalog_config(CLOUD).relaxed_sources == ()


def test_no_connection_identity_is_committed(document):
    # Host, user and password stay in deployment settings; C1-4 keeps them out of the repo.
    assert 'database' not in document
    values = [str(value).lower() for section in document.values() for value in section.values()]
    assert not [v for v in values if 'supabase' in v or 'pooler' in v]


def test_no_keyed_provider_is_configured():
    # finnhub needs FINNHUB_API_KEY; the cloud service must not require any provider key.
    config = load_quote_config(CLOUD)
    assert 'finnhub' not in (config.valuation, *config.comparison)


def test_migrations_are_readable_as_package_resources():
    # C2-7: storage.py loads them through importlib.resources, so they must ship with the package.
    migrations = files('stock_quote_fetcher').joinpath('migrations')
    names = sorted(entry.name for entry in migrations.iterdir() if entry.name.endswith('.sql'))
    assert names and all(migrations.joinpath(name).read_text(encoding='utf-8').strip() for name in names)

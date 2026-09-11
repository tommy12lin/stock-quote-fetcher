"""Issuer-verified OTC supplements absent from Nasdaq symbol directories.

Keep additions explicit and source-backed; never infer a security from its ticker.
The dashboard uses these entries; the observation campaign catalog is unchanged.
"""
from stock_quote_fetcher.instruments import CatalogInstrument


# Verified 2026-09-10: sponsored Level I ADS, one ADS per ordinary share,
# USD trading on OTCQX. Source: issuer investor-relations share information.
SOURCES = {
    'IFNNY': 'https://www.infineon.com/about/investor/infineon-share',
}
ENTRIES = (
    CatalogInstrument('us:otcqx:IFNNY', 'IFNNY', 'US', 'USD', 'OTCQX',
                      'stock', 'Infineon Technologies AG — ADS', {'yahoo': 'IFNNY'}),
)


def supplement(entries):
    entries = tuple(entries)
    # Prefer current directory data if the security becomes exchange-listed.
    aliases = {(entry.market, alias) for entry in entries for alias in entry.aliases}
    return entries + tuple(entry for entry in ENTRIES
                           if not any((entry.market, alias) in aliases for alias in entry.aliases))

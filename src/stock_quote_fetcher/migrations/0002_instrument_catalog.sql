CREATE TABLE {schema}.instrument_catalog_generations (
 id uuid PRIMARY KEY, created_at timestamptz NOT NULL, completed_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL, sources jsonb NOT NULL,
 CHECK (expires_at > completed_at)
);
CREATE INDEX instrument_catalog_current_idx
 ON {schema}.instrument_catalog_generations(completed_at DESC);

CREATE TABLE {schema}.catalog_instruments (
 generation_id uuid NOT NULL REFERENCES {schema}.instrument_catalog_generations(id),
 source text NOT NULL, instrument_id text NOT NULL, ticker text NOT NULL,
 market text NOT NULL CHECK (market IN ('TW','US')), currency text NOT NULL CHECK (currency IN ('TWD','USD')),
 exchange text NOT NULL, asset_type text NOT NULL CHECK (asset_type IN ('stock','etf')),
 name text NOT NULL, provider_symbols jsonb NOT NULL, aliases jsonb NOT NULL,
 PRIMARY KEY(generation_id,instrument_id), UNIQUE(generation_id,market,ticker)
);
CREATE INDEX catalog_instruments_lookup_idx
 ON {schema}.catalog_instruments(generation_id,market,ticker);

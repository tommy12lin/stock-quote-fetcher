-- Every exchange rate fetched (U5), kept as history rather than overwriting one value.
-- One unit of base_currency is worth `rate` units of quote_currency. Rates are never
-- typed in by hand; a valuation uses the newest row received for its pair.
CREATE TABLE {schema}.fx_rates (
 id uuid PRIMARY KEY,
 -- No brace quantifier: migrations go through psycopg's sql.SQL.format, which reads braces.
 base_currency text NOT NULL CHECK (base_currency ~ '^[A-Z][A-Z][A-Z]$'),
 quote_currency text NOT NULL CHECK (quote_currency ~ '^[A-Z][A-Z][A-Z]$'),
 rate {schema}.positive_decimal NOT NULL,
 rate_kind text NOT NULL CHECK (rate_kind IN ('market')),
 provider text NOT NULL, provider_symbol text NOT NULL,
 quote_time timestamptz, received_at timestamptz NOT NULL, job_id text,
 CHECK (base_currency <> quote_currency)
);
CREATE INDEX fx_rates_latest_idx ON {schema}.fx_rates(base_currency,quote_currency,received_at DESC);

CREATE DOMAIN {schema}.positive_decimal AS NUMERIC
  CHECK (VALUE > 0 AND VALUE NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric));
CREATE DOMAIN {schema}.nonnegative_decimal AS NUMERIC
  CHECK (VALUE >= 0 AND VALUE NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric));

CREATE TABLE {schema}.campaigns (
 id uuid PRIMARY KEY, planned_start timestamptz NOT NULL, planned_end timestamptz NOT NULL,
 ended_at timestamptz, status text NOT NULL CHECK (status IN ('running','completed','interrupted')),
 input_snapshot text NOT NULL, input_hash text NOT NULL, config_snapshot jsonb NOT NULL, config_hash text NOT NULL,
 source_instruments jsonb NOT NULL, calendar_version text NOT NULL, schedule_version text NOT NULL,
 threshold_version text NOT NULL, maintenance_windows jsonb NOT NULL,
 CHECK (planned_end > planned_start)
);
CREATE TABLE {schema}.scheduled_cycles (
 id uuid PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES {schema}.campaigns(id),
 market text NOT NULL CHECK (market IN ('TW','US')), scheduled_at timestamptz NOT NULL, window_type text NOT NULL,
 UNIQUE(campaign_id,market,scheduled_at), UNIQUE(id,campaign_id,market)
);
CREATE TABLE {schema}.runs (
 id uuid PRIMARY KEY, campaign_id uuid REFERENCES {schema}.campaigns(id),
 started_at timestamptz NOT NULL, ended_at timestamptz, heartbeat_at timestamptz NOT NULL,
 recovered_at timestamptz, status text NOT NULL CHECK (status IN ('running','completed','interrupted')),
 package_version text NOT NULL, image_id text NOT NULL,
 input_snapshot text NOT NULL, input_hash text NOT NULL, config_snapshot jsonb NOT NULL, config_hash text NOT NULL,
 UNIQUE(id,campaign_id)
);
CREATE INDEX runs_campaign_idx ON {schema}.runs(campaign_id);
CREATE TABLE {schema}.holdings (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES {schema}.runs(id), ticker text NOT NULL,
 market text NOT NULL CHECK (market IN ('TW','US')), currency text NOT NULL,
 buy_price {schema}.positive_decimal NOT NULL, quantity {schema}.positive_decimal NOT NULL,
 CHECK ((market='TW' AND currency='TWD' AND quantity=trunc(quantity)) OR (market='US' AND currency='USD')),
 UNIQUE(run_id,ticker), UNIQUE(id,run_id)
);
CREATE TABLE {schema}.cycles (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES {schema}.runs(id), campaign_id uuid,
 scheduled_cycle_id uuid UNIQUE, market text NOT NULL CHECK (market IN ('TW','US')),
 scheduled_at timestamptz NOT NULL, started_at timestamptz NOT NULL, completed_at timestamptz, recovered_at timestamptz,
 status text NOT NULL CHECK (status IN ('running','completed','interrupted','skipped')), reason text,
 FOREIGN KEY(run_id,campaign_id) REFERENCES {schema}.runs(id,campaign_id),
 FOREIGN KEY(scheduled_cycle_id,campaign_id,market) REFERENCES {schema}.scheduled_cycles(id,campaign_id,market),
 CHECK (scheduled_cycle_id IS NULL OR campaign_id IS NOT NULL), UNIQUE(id,run_id)
);
CREATE INDEX cycles_run_idx ON {schema}.cycles(run_id);
CREATE TABLE {schema}.fetch_attempts (
 id uuid PRIMARY KEY, run_id uuid NOT NULL, cycle_id uuid NOT NULL,
 provider text NOT NULL, instrument_id text NOT NULL, ticker text NOT NULL, attempt_number integer NOT NULL CHECK(attempt_number>0),
 started_at timestamptz NOT NULL, completed_at timestamptz, recovered_at timestamptz,
 status text NOT NULL CHECK(status IN ('started','success','timeout','rate_limited','network_error','provider_error','invalid_payload','unsupported_symbol','interrupted')),
 elapsed_ms integer CHECK(elapsed_ms>=0), error_code text, response_hash text, response_evidence jsonb,
 FOREIGN KEY(cycle_id,run_id) REFERENCES {schema}.cycles(id,run_id),
 UNIQUE(cycle_id,provider,instrument_id,attempt_number)
);
CREATE TABLE {schema}.quotes (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL UNIQUE REFERENCES {schema}.fetch_attempts(id),
 instrument_id text NOT NULL, ticker text NOT NULL, provider_symbol text NOT NULL,
 market text NOT NULL CHECK(market IN ('TW','US')), currency text NOT NULL, provider text NOT NULL,
 price {schema}.positive_decimal NOT NULL, price_kind text NOT NULL CHECK(price_kind IN ('last_trade','close','bar_close')),
 quote_time timestamptz, received_at timestamptz NOT NULL, trading_date date,
 session text NOT NULL CHECK(session IN ('regular','closed','unknown','pre_market','post_market')),
 time_precision text NOT NULL CHECK(time_precision IN ('second','millisecond','microsecond','minute','day','unknown')),
 declared_delay_seconds integer CHECK(declared_delay_seconds>=0), quality_flags jsonb NOT NULL,
 source_timezone text, source_time_raw text
);
CREATE INDEX quotes_lookup_idx ON {schema}.quotes(ticker,provider,received_at);
CREATE TABLE {schema}.valuations (
 cycle_id uuid NOT NULL, holding_id uuid NOT NULL, run_id uuid NOT NULL,
 quote_id uuid REFERENCES {schema}.quotes(id), market_value {schema}.nonnegative_decimal,
 quality_flags jsonb NOT NULL, failure_reason text,
 PRIMARY KEY(cycle_id,holding_id),
 FOREIGN KEY(cycle_id,run_id) REFERENCES {schema}.cycles(id,run_id),
 FOREIGN KEY(holding_id,run_id) REFERENCES {schema}.holdings(id,run_id),
 CHECK(market_value IS NULL OR quote_id IS NOT NULL)
);
CREATE TABLE {schema}.valuation_totals (
 cycle_id uuid NOT NULL REFERENCES {schema}.cycles(id), currency text NOT NULL CHECK(currency IN ('TWD','USD')),
 known_subtotal {schema}.nonnegative_decimal NOT NULL, total {schema}.nonnegative_decimal,
 holding_count integer NOT NULL CHECK(holding_count>0), valued_count integer NOT NULL CHECK(valued_count>=0),
 missing_count integer NOT NULL CHECK(missing_count>=0), degraded_count integer NOT NULL CHECK(degraded_count BETWEEN 0 AND valued_count),
 completeness text NOT NULL CHECK(completeness IN ('complete','degraded','partial','unavailable')),
 PRIMARY KEY(cycle_id,currency), CHECK(holding_count=valued_count+missing_count),
 CHECK ((missing_count=0 AND total IS NOT NULL AND total=known_subtotal) OR (missing_count>0 AND total IS NULL)),
 CHECK ((completeness='unavailable' AND valued_count=0) OR
        (completeness='partial' AND valued_count>0 AND missing_count>0) OR
        (completeness='degraded' AND missing_count=0 AND degraded_count>0) OR
        (completeness='complete' AND missing_count=0 AND degraded_count=0))
);

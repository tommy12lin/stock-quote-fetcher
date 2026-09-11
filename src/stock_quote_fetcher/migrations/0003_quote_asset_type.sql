-- Official security type of the quoted instrument. Nullable because quotes written before
-- this version have no recorded type; reports must keep treating those as undetermined.
ALTER TABLE {schema}.quotes
 ADD COLUMN asset_type text CHECK (asset_type IN ('stock','etf'));

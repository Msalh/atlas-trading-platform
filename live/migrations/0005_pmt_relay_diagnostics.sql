-- PickMyTrade relay diagnostics: full instrumentation of the LATEST relay attempt
-- (destination URL, masked payload, HTTP status code, response body, exception,
-- duration) for a given trade - added to debug why PickMyTrade's own Alert Log showed
-- nothing for a relay Atlas believed succeeded. Stores only the most recent attempt
-- per trade (overwritten each time this trade is re-forwarded), not a full history -
-- same TEXT-column/JSON-at-repository-boundary pattern as ai_notes.factors_json (see
-- migrations/0004_ai_intelligence_fields.sql). Purely additive - does not change
-- pmt_forwarded/pmt_status_code/pmt_error's existing meaning or population.

ALTER TABLE trades ADD COLUMN IF NOT EXISTS pmt_relay_diagnostics TEXT;

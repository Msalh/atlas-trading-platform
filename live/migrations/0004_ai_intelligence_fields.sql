-- AI Intelligence (Sprint 7): structured, historically-grounded fields on ai_notes,
-- populated by atlas/intelligence.py's deterministic retrieval + statistics (not
-- machine learning - see that module's docstring). Only meaningful for note_type
-- 'entry_score' - NULL for post_trade_review/daily_report/weekly_report rows.
--
-- factors_json is a JSON-encoded list of the measurable factors (regime slope, EMA
-- distance, sweep age) compared against the historical similar-trade sample, e.g.
-- [{"name": "regime_slope_pct", "entry_value": 1.4, "winners_median": 1.1,
--   "losers_median": 0.5, "favorable": true}, ...] - stored as TEXT (same pattern as
-- trades.raw_entry_payload) rather than a native JSONB column, decoded at the
-- repository boundary so callers always see a real Python list, never a JSON string.

ALTER TABLE ai_notes ADD COLUMN IF NOT EXISTS expected_r DOUBLE PRECISION;
ALTER TABLE ai_notes ADD COLUMN IF NOT EXISTS historical_win_rate_pct DOUBLE PRECISION;
ALTER TABLE ai_notes ADD COLUMN IF NOT EXISTS similar_trade_count INTEGER;
ALTER TABLE ai_notes ADD COLUMN IF NOT EXISTS factors_json TEXT;

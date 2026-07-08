-- AI Copilot output (Sprint 6): one row per AI pass, not squeezed into the trades
-- table's old single llm_model/llm_analysis/llm_error columns (which only ever held
-- one note per trade - fine for a single entry-time comment, not enough once a trade
-- also gets a post-trade review, and reports aren't tied to any one trade at all).
--
-- trade_correlation_id is NULL for report-type notes (daily_report/weekly_report),
-- which summarize many trades rather than belonging to one. The old trades.llm_*
-- columns are left in place, untouched, as a read-only record of pre-Sprint-6 entries
-- - nothing new is ever written there (see atlas/ai.py).

CREATE TABLE IF NOT EXISTS ai_notes (
    id                      BIGSERIAL PRIMARY KEY,
    trade_correlation_id   TEXT REFERENCES trades(correlation_id),
    note_type               TEXT NOT NULL,  -- 'entry_score' | 'post_trade_review' | 'daily_report' | 'weekly_report'
    created_at               TEXT NOT NULL,
    model                    TEXT,
    score                    INTEGER,        -- 1-10, only meaningful for 'entry_score'
    score_label              TEXT,           -- e.g. "Strong Alignment", only meaningful for 'entry_score'
    content                  TEXT,
    error                    TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_notes_trade ON ai_notes (trade_correlation_id);
CREATE INDEX IF NOT EXISTS idx_ai_notes_type ON ai_notes (note_type);
CREATE INDEX IF NOT EXISTS idx_ai_notes_created_at ON ai_notes (created_at);

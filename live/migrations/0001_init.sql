-- Initial schema for Atlas: the trades table, mirroring the Sprint 0 SQLite schema
-- column-for-column so the data migration script
-- (scripts/migrate_sqlite_to_postgres.py) can do a straight one-to-one copy.
--
-- received_at/signal_time/last_update_at/closed_at are kept as TEXT (ISO-8601
-- strings), matching how Sprint 0 stored them, rather than TIMESTAMPTZ - changing
-- that is a real improvement but out of scope for this sprint (see
-- docs/sprint1/architecture-decisions.md) and would touch dashboard rendering and
-- test assertions for no behavioral benefit yet.

CREATE TABLE IF NOT EXISTS trades (
    id                  BIGSERIAL PRIMARY KEY,
    correlation_id      TEXT UNIQUE NOT NULL,
    received_at         TEXT NOT NULL,
    signal_time         TEXT,
    direction           TEXT,
    setup_tag           TEXT,
    symbol              TEXT,
    entry_price         DOUBLE PRECISION,
    sl                  DOUBLE PRECISION,
    tp                  DOUBLE PRECISION,
    atr                 DOUBLE PRECISION,
    ema_distance_atr    DOUBLE PRECISION,
    regime_slope_pct    DOUBLE PRECISION,
    sweep_age_bars      INTEGER,
    session             TEXT,

    status              TEXT NOT NULL DEFAULT 'open',
    current_price       DOUBLE PRECISION,
    unrealized_pnl      DOUBLE PRECISION,
    last_update_at      TEXT,
    exit_price          DOUBLE PRECISION,
    realized_pnl        DOUBLE PRECISION,
    closed_at           TEXT,

    llm_model           TEXT,
    llm_analysis        TEXT,
    llm_error           TEXT,

    pmt_forwarded       BOOLEAN NOT NULL DEFAULT FALSE,
    pmt_status_code     INTEGER,
    pmt_error           TEXT,

    raw_entry_payload   TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_correlation_id ON trades (correlation_id);
CREATE INDEX IF NOT EXISTS idx_trades_received_at ON trades (received_at);

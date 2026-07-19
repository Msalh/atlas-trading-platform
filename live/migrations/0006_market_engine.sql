-- Market Engine event store - Sprint 3. Append-only: rows are inserted, never
-- updated or deleted, by any code path in this Sprint or any planned future
-- one (see the project architecture review's "append-only, immutable event
-- history" principle). "Latest state" and "history" are queries over this
-- table (Sprint 4), never a separately-maintained mutable row.
--
-- Idempotency key is (symbol, timeframe, event_id) - matches
-- atlas.market_engine.ports.MarketStateRepository's documented contract
-- exactly, and is enforced here at the database level via UNIQUE, not just in
-- application code, so a concurrent duplicate insert is safe without any
-- advisory lock (see atlas/market_engine/repositories/postgres.py's own
-- docstring for why this table doesn't need the lock
-- PostgresTradeRepository.claim_and_forward uses - there is no non-idempotent
-- side effect here to protect).
--
-- Timestamps are TEXT (ISO-8601), matching the trades table's own established
-- convention (see migrations/0001_init.sql) - full precision (not
-- second-truncated) for occurred_at/received_at specifically, since these are
-- meant to support exact replay later, not just an approximate "when did this
-- happen" the way trades' administrative timestamps are.
--
-- No secondary index is added in this Sprint beyond what UNIQUE already
-- creates. Sprint 3's own scope is ingestion only ("no read endpoints") - an
-- index that only serves a query (get_latest/get_history) nothing calls yet
-- would be exactly the premature optimization this project now explicitly
-- avoids. That index belongs in Sprint 4's own migration, added alongside the
-- query it actually serves.

CREATE TABLE IF NOT EXISTS market_state_events (
    id                              BIGSERIAL PRIMARY KEY,
    event_id                        TEXT NOT NULL,
    symbol                          TEXT NOT NULL,
    timeframe                       TEXT NOT NULL,
    schema_version                  TEXT NOT NULL,
    event_type                      TEXT NOT NULL,
    source                          TEXT NOT NULL,
    occurred_at                     TEXT NOT NULL,
    received_at                     TEXT NOT NULL,
    bar_status                      TEXT NOT NULL,

    open                            DOUBLE PRECISION,
    high                            DOUBLE PRECISION,
    low                             DOUBLE PRECISION,
    close                           DOUBLE PRECISION,
    volume                          DOUBLE PRECISION,

    session_name                    TEXT,
    is_rth                          BOOLEAN,
    trading_date                    TEXT,
    rth_open                        DOUBLE PRECISION,
    previous_day_high               DOUBLE PRECISION,
    previous_day_low                DOUBLE PRECISION,
    overnight_high                  DOUBLE PRECISION,
    overnight_low                   DOUBLE PRECISION,

    vwap                            DOUBLE PRECISION,
    distance_from_vwap_points       DOUBLE PRECISION,
    atr                             DOUBLE PRECISION,
    volume_ratio                    DOUBLE PRECISION,

    nearest_liquidity_level         DOUBLE PRECISION,
    nearest_liquidity_type          TEXT,
    distance_to_liquidity_ticks     DOUBLE PRECISION,
    overnight_high_status           TEXT,
    overnight_low_status            TEXT,
    previous_day_high_status        TEXT,
    previous_day_low_status         TEXT,

    trend_1m                        TEXT,
    trend_5m                        TEXT,
    trend_15m                       TEXT,
    trend_1h                        TEXT,

    liquidity_sweep                 BOOLEAN,
    reclaim                         BOOLEAN,
    rejection                       BOOLEAN,
    displacement                    BOOLEAN,
    volume_spike                    BOOLEAN,

    raw_payload                     TEXT NOT NULL,

    CONSTRAINT uq_market_state_events_symbol_timeframe_event_id
        UNIQUE (symbol, timeframe, event_id)
);

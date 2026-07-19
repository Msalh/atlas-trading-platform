-- Serves exactly two queries, both added in this same Sprint (Sprint 4):
-- PostgresMarketStateRepository.get_latest and .get_history, both shaped
-- "WHERE symbol = ? AND timeframe = ? ORDER BY occurred_at DESC [LIMIT ?]" -
-- see atlas/market_engine/repositories/postgres.py's _SELECT_LATEST_SQL and
-- _SELECT_HISTORY_SQL.
--
-- This index did NOT belong in migrations/0006_market_engine.sql (Sprint 3):
-- that Sprint's own scope was ingestion only, and no query existed yet for an
-- index to serve - adding one ahead of the query it serves would have been
-- exactly the premature optimization the project charter now explicitly
-- forbids ("do not optimize... unless a measurement demonstrates a real
-- bottleneck"). This is not premature: the query exists, in this same
-- migration's own Sprint, and a query filtering + sorting by these three
-- columns is otherwise a full table scan plus an in-memory sort - not a
-- hypothetical cost, a mechanical one, for the exact access pattern this
-- Sprint introduces.
--
-- Column order matters: symbol and timeframe are equality-filtered (most
-- selective first), occurred_at DESC lets Postgres satisfy "ORDER BY
-- occurred_at DESC LIMIT n" directly from the index without a separate sort
-- step.
--
-- Additive and safe: CREATE INDEX IF NOT EXISTS on an existing table with no
-- other index of this shape - does not alter, lock out writers for longer
-- than a normal DDL statement (the table is new and empty relative to any
-- real production load at this stage), and does not change any existing
-- query's behavior, only adds a new access path.

CREATE INDEX IF NOT EXISTS idx_market_state_events_symbol_timeframe_occurred_at
    ON market_state_events (symbol, timeframe, occurred_at DESC);

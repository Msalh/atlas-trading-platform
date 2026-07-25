-- Phase 17C: isolated append-only TraderNow evidence snapshot store.
-- Runtime services receive role membership separately; these are NOLOGIN
-- privilege templates and therefore contain no credentials.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_snapshot_admin') THEN
        CREATE ROLE atlas_snapshot_admin NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_snapshot_retention') THEN
        CREATE ROLE atlas_snapshot_retention NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_snapshot_writer') THEN
        CREATE ROLE atlas_snapshot_writer NOLOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_snapshot_reader') THEN
        CREATE ROLE atlas_snapshot_reader NOLOGIN NOINHERIT;
    END IF;
END
$$;

DO $$
BEGIN
    EXECUTE format(
        'GRANT atlas_snapshot_admin TO %I WITH ADMIN OPTION',
        current_user
    );
END
$$;

CREATE SCHEMA IF NOT EXISTS atlas_snapshot AUTHORIZATION atlas_snapshot_admin;

SET ROLE atlas_snapshot_admin;

CREATE TABLE IF NOT EXISTS atlas_snapshot.snapshots (
    snapshot_id UUID PRIMARY KEY,
    snapshot_schema_version TEXT NOT NULL
        CHECK (snapshot_schema_version = 'trader_now_snapshot.v1'),
    evidence_profile TEXT NOT NULL
        CHECK (evidence_profile = 'trader_now_complete.v1'),
    canonicalization_profile TEXT NOT NULL
        CHECK (canonicalization_profile = 'atlas-jcs.v1'),
    evidence_digest TEXT NOT NULL UNIQUE
        CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (idempotency_key ~ '^tns1:[0-9a-f]{64}$'),

    -- The one and only authoritative snapshot representation.
    canonical_payload BYTEA NOT NULL
        CHECK (octet_length(canonical_payload) > 0),

    -- Everything below is a non-authoritative index projection derived from
    -- canonical_payload and reverified by the repository after every read.
    created_at TIMESTAMPTZ NOT NULL,
    evaluated_at TIMESTAMPTZ,
    latest_closed_at TIMESTAMPTZ,
    economic_instrument TEXT,
    market_data_provider TEXT,
    market_data_series_symbol TEXT,
    market_data_series_type TEXT,
    timeframe TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    trust_status TEXT NOT NULL,
    supersedes_snapshot_id UUID REFERENCES atlas_snapshot.snapshots(snapshot_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CHECK (supersedes_snapshot_id IS NULL OR supersedes_snapshot_id <> snapshot_id)
);

CREATE INDEX IF NOT EXISTS snapshots_created_order_idx
    ON atlas_snapshot.snapshots (created_at DESC, snapshot_id DESC);
CREATE INDEX IF NOT EXISTS snapshots_identity_time_idx
    ON atlas_snapshot.snapshots (
        economic_instrument,
        market_data_provider,
        market_data_series_symbol,
        timeframe,
        latest_closed_at DESC
    );
CREATE INDEX IF NOT EXISTS snapshots_supersedes_idx
    ON atlas_snapshot.snapshots (supersedes_snapshot_id)
    WHERE supersedes_snapshot_id IS NOT NULL;

CREATE OR REPLACE FUNCTION atlas_snapshot.reject_snapshot_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'atlas snapshots are immutable; corrections require a new snapshot'
        USING ERRCODE = '55000';
END
$$;

DROP TRIGGER IF EXISTS snapshots_reject_update ON atlas_snapshot.snapshots;
CREATE TRIGGER snapshots_reject_update
BEFORE UPDATE ON atlas_snapshot.snapshots
FOR EACH ROW EXECUTE FUNCTION atlas_snapshot.reject_snapshot_update();

RESET ROLE;

REVOKE ALL ON SCHEMA atlas_snapshot FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA atlas_snapshot FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA atlas_snapshot FROM PUBLIC;

GRANT USAGE ON SCHEMA atlas_snapshot
    TO atlas_snapshot_writer, atlas_snapshot_reader, atlas_snapshot_retention;
GRANT SELECT, INSERT ON atlas_snapshot.snapshots TO atlas_snapshot_writer;
GRANT SELECT ON atlas_snapshot.snapshots TO atlas_snapshot_reader;
GRANT SELECT, DELETE ON atlas_snapshot.snapshots TO atlas_snapshot_retention;
GRANT EXECUTE ON FUNCTION atlas_snapshot.reject_snapshot_update()
    TO atlas_snapshot_admin;

ALTER DEFAULT PRIVILEGES FOR ROLE atlas_snapshot_admin
    IN SCHEMA atlas_snapshot REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE atlas_snapshot_admin
    IN SCHEMA atlas_snapshot REVOKE ALL ON FUNCTIONS FROM PUBLIC;

DO $$
BEGIN
    EXECUTE format('REVOKE atlas_snapshot_admin FROM %I', current_user);
END
$$;

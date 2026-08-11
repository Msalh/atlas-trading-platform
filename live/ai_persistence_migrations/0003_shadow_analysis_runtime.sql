-- Stable Shadow-analysis idempotency claims and read indexes.
DO $$ BEGIN EXECUTE format(
    'GRANT atlas_ai_persistence_owner TO %I WITH ADMIN OPTION', current_user
); END $$;
SET ROLE atlas_ai_persistence_owner;
CREATE TABLE atlas_ai_persistence.shadow_analysis_claims (
    snapshot_id UUID PRIMARY KEY,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE FUNCTION atlas_ai_persistence.reject_shadow_claim_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Shadow analysis claims are immutable' USING ERRCODE = '55000';
END $$;
CREATE TRIGGER shadow_analysis_claims_reject_update_delete
BEFORE UPDATE OR DELETE ON atlas_ai_persistence.shadow_analysis_claims
FOR EACH ROW EXECUTE FUNCTION atlas_ai_persistence.reject_shadow_claim_mutation();
CREATE INDEX persistence_records_snapshot_history_idx
ON atlas_ai_persistence.persistence_records
    (snapshot_id, audit_recorded_at DESC, analysis_audit_id DESC);
RESET ROLE;
REVOKE ALL ON atlas_ai_persistence.shadow_analysis_claims FROM PUBLIC;
GRANT SELECT, INSERT ON atlas_ai_persistence.shadow_analysis_claims
TO atlas_ai_persistence_writer;
GRANT SELECT ON atlas_ai_persistence.shadow_analysis_claims
TO atlas_ai_persistence_reader;
GRANT EXECUTE ON FUNCTION atlas_ai_persistence.reject_shadow_claim_mutation()
TO atlas_ai_persistence_owner;
DO $$ BEGIN EXECUTE format(
    'REVOKE atlas_ai_persistence_owner FROM %I', current_user
); END $$;

-- Phase 18G: isolated, immutable AI-analysis persistence schema.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_ai_persistence_owner') THEN CREATE ROLE atlas_ai_persistence_owner NOLOGIN NOINHERIT; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_ai_persistence_writer') THEN CREATE ROLE atlas_ai_persistence_writer NOLOGIN NOINHERIT; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_ai_persistence_reader') THEN CREATE ROLE atlas_ai_persistence_reader NOLOGIN NOINHERIT; END IF;
END $$;
DO $$ BEGIN EXECUTE format('GRANT atlas_ai_persistence_owner TO %I WITH ADMIN OPTION', current_user); END $$;
CREATE SCHEMA atlas_ai_persistence AUTHORIZATION atlas_ai_persistence_owner;
SET ROLE atlas_ai_persistence_owner;
CREATE TABLE atlas_ai_persistence.persistence_records (
    analysis_audit_id UUID PRIMARY KEY,
    analysis_output_id UUID,
    outcome TEXT NOT NULL CHECK (outcome IN ('completed', 'failed', 'refused')),
    analysis_input_id UUID,
    snapshot_id UUID NOT NULL,
    evidence_digest TEXT NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    purpose TEXT NOT NULL,
    input_contract_version TEXT NOT NULL CHECK (input_contract_version = 'ai_analysis_input.v1'),
    output_contract_version TEXT NOT NULL CHECK (output_contract_version = 'ai_analysis_output.v1'),
    policy_contract_version TEXT NOT NULL CHECK (policy_contract_version = 'ai_analysis_policy.v1'),
    provider_id TEXT,
    model_id TEXT,
    audit_recorded_at TIMESTAMPTZ NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    persistence_schema_version TEXT NOT NULL CHECK (persistence_schema_version = 'atlas_ai_persistence.v1'),
    canonicalization_profile TEXT NOT NULL CHECK (canonicalization_profile = 'atlas-ai-canonical-json.v1'),
    audit_payload BYTEA NOT NULL CHECK (octet_length(audit_payload) > 0),
    audit_digest TEXT NOT NULL CHECK (audit_digest ~ '^[0-9a-f]{64}$'),
    output_payload BYTEA,
    output_digest TEXT,
    CHECK ((outcome = 'completed' AND analysis_output_id IS NOT NULL AND analysis_input_id IS NOT NULL AND provider_id IS NOT NULL AND model_id IS NOT NULL AND output_payload IS NOT NULL AND output_digest ~ '^[0-9a-f]{64}$') OR (outcome IN ('failed', 'refused') AND analysis_output_id IS NULL AND output_payload IS NULL AND output_digest IS NULL))
);
CREATE UNIQUE INDEX persistence_records_output_id_uq ON atlas_ai_persistence.persistence_records (analysis_output_id) WHERE analysis_output_id IS NOT NULL;
CREATE INDEX persistence_records_retention_idx ON atlas_ai_persistence.persistence_records (audit_recorded_at, analysis_audit_id);
CREATE FUNCTION atlas_ai_persistence.reject_record_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'AI persistence records are immutable' USING ERRCODE = '55000'; END $$;
CREATE TRIGGER persistence_records_reject_update_delete BEFORE UPDATE OR DELETE ON atlas_ai_persistence.persistence_records FOR EACH ROW EXECUTE FUNCTION atlas_ai_persistence.reject_record_mutation();
RESET ROLE;
REVOKE ALL ON SCHEMA atlas_ai_persistence FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA atlas_ai_persistence FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA atlas_ai_persistence FROM PUBLIC;
GRANT USAGE ON SCHEMA atlas_ai_persistence TO atlas_ai_persistence_writer, atlas_ai_persistence_reader;
GRANT SELECT, INSERT ON atlas_ai_persistence.persistence_records TO atlas_ai_persistence_writer;
GRANT SELECT ON atlas_ai_persistence.persistence_records TO atlas_ai_persistence_reader;
GRANT EXECUTE ON FUNCTION atlas_ai_persistence.reject_record_mutation() TO atlas_ai_persistence_owner;
ALTER DEFAULT PRIVILEGES FOR ROLE atlas_ai_persistence_owner IN SCHEMA atlas_ai_persistence REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE atlas_ai_persistence_owner IN SCHEMA atlas_ai_persistence REVOKE ALL ON FUNCTIONS FROM PUBLIC;
DO $$ BEGIN EXECUTE format('REVOKE atlas_ai_persistence_owner FROM %I', current_user); END $$;

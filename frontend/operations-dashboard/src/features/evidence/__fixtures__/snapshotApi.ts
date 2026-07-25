import {
  SNAPSHOT_API_SCHEMA_VERSION,
  type SnapshotDetailResponse,
  type SnapshotErrorResponse,
  type SnapshotIntegrityResponse,
  type SnapshotListResponse,
  type SnapshotMetadata,
} from "../contract";

export const SYNTHETIC_SNAPSHOT_ID =
  "019b1111-2222-7333-8444-555555555555";
export const SYNTHETIC_SECOND_SNAPSHOT_ID =
  "019b1111-2222-7333-8444-666666666666";
export const SYNTHETIC_DIGEST = "a".repeat(64);
export const SYNTHETIC_CORRELATION_ID = "fixture-correlation-17f-0001";
export const SYNTHETIC_OPAQUE_CURSOR = "fixture-opaque-cursor.do-not-decode";

export const snapshotMetadataFixture: SnapshotMetadata = {
  schema_version: SNAPSHOT_API_SCHEMA_VERSION,
  snapshot_id: SYNTHETIC_SNAPSHOT_ID,
  evidence_digest: SYNTHETIC_DIGEST,
  created_at: "2030-01-02T03:04:06.000000Z",
  evaluated_at: "2030-01-02T03:04:05.000000Z",
  latest_closed_at: "2030-01-02T03:00:00.000000Z",
  economic_instrument: "MNQ",
  market_data_provider: "synthetic-provider",
  market_data_series_symbol: "SYNTHETIC:MNQ-CONTINUOUS",
  market_data_series_type: "continuous",
  timeframe: "5m",
  strategy_id: "displacement_volume_context",
  strategy_version: "displacement-volume-context.fixture.v1",
  trust_status: "trusted",
  supersedes_snapshot_id: null,
};

export const snapshotListFixture: SnapshotListResponse = {
  schema_version: SNAPSHOT_API_SCHEMA_VERSION,
  items: [snapshotMetadataFixture],
  next_cursor: SYNTHETIC_OPAQUE_CURSOR,
};

export const emptySnapshotListFixture: SnapshotListResponse = {
  schema_version: SNAPSHOT_API_SCHEMA_VERSION,
  items: [],
  next_cursor: null,
};

export const snapshotDetailFixture: SnapshotDetailResponse = {
  schema_version: SNAPSHOT_API_SCHEMA_VERSION,
  snapshot: {
    canonicalization_profile: "atlas-jcs.v1",
    created_at: snapshotMetadataFixture.created_at,
    evidence: {
      availability: {
        context: { reason_codes: [], status: "available" },
        interpretations: { reason_codes: [], status: "available" },
        market: { reason_codes: [], status: "available" },
        market_history: { reason_codes: [], status: "available" },
        rules: { reason_codes: [], status: "available" },
        setups: { reason_codes: [], status: "available" },
        strategy: { reason_codes: [], status: "available" },
      },
      context: {
        availability: { reason_codes: [], status: "available" },
        data: {
          classifier_version: "market-context.fixture.v1",
          quality: "trusted",
          symbol: "SYNTHETIC:MNQ-CONTINUOUS",
          timeframe: "5m",
        },
      },
      decision: { availability: "not_implemented", state: null },
      evaluated_at: snapshotMetadataFixture.evaluated_at,
      identity: {
        product: "MNQ",
        strategy_id: snapshotMetadataFixture.strategy_id,
        strategy_version: snapshotMetadataFixture.strategy_version,
        symbol: "MNQ",
        timeframe: "5m",
      },
      input_snapshot_at: snapshotMetadataFixture.latest_closed_at,
      interpretations: {
        availability: { reason_codes: [], status: "available" },
        interpretations: [
          {
            detected: true,
            direction: "long",
            reason_codes: ["fixture_alignment"],
            setup_id: "synthetic_displacement",
          },
        ],
      },
      market: {
        availability: { reason_codes: [], status: "available" },
        bar_count: 288,
        economic_instrument: { symbol: "MNQ" },
        history_availability: { reason_codes: [], status: "available" },
        latest_closed_at: snapshotMetadataFixture.latest_closed_at,
        listed_instrument: null,
        market_data_series: {
          provider: snapshotMetadataFixture.market_data_provider,
          resolution_version: "synthetic-resolution.fixture.v1",
          resolved_at: snapshotMetadataFixture.evaluated_at,
          series_type: snapshotMetadataFixture.market_data_series_type,
          symbol: snapshotMetadataFixture.market_data_series_symbol,
        },
      },
      risk: null,
      rules: {
        availability: { reason_codes: [], status: "available" },
        facts: [
          {
            definition_version: "rule.fixture.v1",
            fact_id: "synthetic_fact",
            reason: null,
            status: "computed",
            value: true,
          },
        ],
        occurred_at: snapshotMetadataFixture.latest_closed_at,
        schema_version: "rule_engine.v1",
        symbol: "SYNTHETIC:MNQ-CONTINUOUS",
        timeframe: "5m",
      },
      setups: {
        availability: { reason_codes: [], status: "available" },
        occurred_at: snapshotMetadataFixture.latest_closed_at,
        schema_version: "setup_engine.v1",
        setups: [
          {
            definition_version: "setup.fixture.v1",
            detected: true,
            reason: null,
            setup_id: "synthetic_displacement",
            severity: "high",
            status: "computed",
            supporting_fact_ids: ["synthetic_fact"],
          },
        ],
        symbol: "SYNTHETIC:MNQ-CONTINUOUS",
        timeframe: "5m",
      },
      source_trust: {
        availability: "available",
        freshness: {
          evaluated_at: snapshotMetadataFixture.evaluated_at,
          latest_closed_at: snapshotMetadataFixture.latest_closed_at,
          reason_codes: [],
          status: "current",
        },
        overall: "trusted",
        reason_codes: [],
        structural_validity: "valid",
      },
      strategy: {
        availability: { reason_codes: [], status: "available" },
        decisions: [
          {
            confidence: "0.80",
            direction: "long",
            disposition: "candidate",
            reason_codes: ["fixture_alignment"],
            setup_ids: ["synthetic_displacement"],
            strategy_id: snapshotMetadataFixture.strategy_id,
            strategy_version: snapshotMetadataFixture.strategy_version,
          },
        ],
      },
      trust: {
        policy_version: "freshness.fixture.v1",
        reason_codes: [],
        status: "trusted",
      },
    },
    evidence_profile: "trader_now_complete.v1",
    idempotency_key: `tns1:${"b".repeat(64)}`,
    integrity: {
      algorithm: "sha256",
      evidence_digest: SYNTHETIC_DIGEST,
    },
    snapshot_id: SYNTHETIC_SNAPSHOT_ID,
    snapshot_schema_version: "trader_now_snapshot.v1",
    source: {
      trader_now_domain_schema_version: "trader_now.v2",
      trader_now_response_schema_version: "trader_now_response.v2",
    },
    supersedes_snapshot_id: null,
  },
};

export const snapshotIntegrityFixture: SnapshotIntegrityResponse = {
  schema_version: SNAPSHOT_API_SCHEMA_VERSION,
  snapshot_id: SYNTHETIC_SNAPSHOT_ID,
  evidence_digest: SYNTHETIC_DIGEST,
  valid: true,
};

export const snapshotErrorFixtures = {
  unauthorized: {
    schema_version: SNAPSHOT_API_SCHEMA_VERSION,
    code: "authentication_required",
    message: "authentication is required",
    correlation_id: SYNTHETIC_CORRELATION_ID,
  },
  notFound: {
    schema_version: SNAPSHOT_API_SCHEMA_VERSION,
    code: "snapshot_not_found",
    message: "snapshot was not found",
    correlation_id: SYNTHETIC_CORRELATION_ID,
  },
  integrityFailure: {
    schema_version: SNAPSHOT_API_SCHEMA_VERSION,
    code: "snapshot_integrity_failed",
    message: "snapshot integrity verification failed",
    correlation_id: SYNTHETIC_CORRELATION_ID,
  },
  unavailable: {
    schema_version: SNAPSHOT_API_SCHEMA_VERSION,
    code: "snapshot_store_unavailable",
    message: "snapshot store is unavailable",
    correlation_id: SYNTHETIC_CORRELATION_ID,
  },
} as const satisfies Readonly<Record<string, SnapshotErrorResponse>>;

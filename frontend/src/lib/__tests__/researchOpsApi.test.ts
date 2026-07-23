import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deriveCandidateStatus,
  deriveEntryPromotionStatus,
  fetchLatestSnapshot,
  fetchLineage,
  fetchOpsStatus,
  fetchPromotionCandidates,
  fetchPromotionHistory,
  PromotionRecordSummary,
} from "@/lib/researchOpsApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

describe("fetchOpsStatus", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses a ready ledger", async () => {
    mockFetchOnce({
      database: { ok: true, reason: null, detail: "ok" },
      research_ledger: {
        status: "ready",
        reason: null,
        checks: {
          configuration_valid: { ok: true, reason: null, detail: null },
          ledger_directory: { ok: true, reason: null, detail: null },
          volume_mounted: { ok: true, reason: null, detail: null },
          jsonl_stores_initialized: { ok: true, reason: null, detail: null },
          registries_available: { ok: true, reason: null, detail: null },
        },
      },
    });
    const result = await fetchOpsStatus();
    expect(result.research_ledger.status).toBe("ready");
    expect(result.database.ok).toBe(true);
  });

  it("parses a degraded ledger with a reason code", async () => {
    mockFetchOnce({
      database: { ok: true, reason: null, detail: "ok" },
      research_ledger: {
        status: "degraded",
        reason: "research_ledger_not_configured",
        checks: {
          configuration_valid: { ok: false, reason: "research_ledger_not_configured", detail: "RESEARCH_LEDGER_DIR is not set" },
        },
      },
    });
    const result = await fetchOpsStatus();
    expect(result.research_ledger.status).toBe("degraded");
    expect(result.research_ledger.reason).toBe("research_ledger_not_configured");
  });

  it("rejects a response missing research_ledger", async () => {
    mockFetchOnce({ database: { ok: true, reason: null, detail: "ok" } });
    await expect(fetchOpsStatus()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchLatestSnapshot", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses a snapshot with entries", async () => {
    mockFetchOnce({
      ok: true,
      snapshot_id: "snap_1",
      created_at: "2026-07-23T00:00:00Z",
      ranking_policy_id: "v1",
      ranking_policy_version: "1.0",
      entries: [
        { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1" },
      ],
    });
    const result = await fetchLatestSnapshot();
    expect(result.snapshot_id).toBe("snap_1");
    expect(result.entries).toHaveLength(1);
    expect(result.entries[0].realization_id).toBe("r1");
  });

  it("parses a decision-free entry (realization_id/validation_id null)", async () => {
    mockFetchOnce({
      ok: true,
      snapshot_id: "snap_2",
      created_at: "2026-07-23T00:00:00Z",
      ranking_policy_id: null,
      ranking_policy_version: null,
      entries: [{ hypothesis_id: "h1", realization_id: null, rank: 1, score: 1.0, validation_id: "v1" }],
    });
    const result = await fetchLatestSnapshot();
    expect(result.entries[0].realization_id).toBeNull();
  });

  it("throws not_found when no snapshot has ever been recorded (404)", async () => {
    mockFetchOnce({ ok: false, error: "no leaderboard snapshots have been recorded yet" }, 404);
    await expect(fetchLatestSnapshot()).rejects.toMatchObject({ kind: "not_found" });
  });

  it("throws upstream_error when the Ledger is degraded (503)", async () => {
    mockFetchOnce({ ok: false, error: "research ledger storage is degraded: research_ledger_not_configured", reason: "research_ledger_not_configured" }, 503);
    await expect(fetchLatestSnapshot()).rejects.toMatchObject({ kind: "upstream_error" });
  });
});

describe("fetchPromotionHistory", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses a non-empty history", async () => {
    mockFetchOnce({
      ok: true,
      records: [
        { promotion_id: "p1", hypothesis_id: "h1", realization_id: "r1", decision: "approved", decided_at: "2026-07-23T00:00:00Z", reviewer: "alice", rationale: "strong out-of-sample edge", evidence_snapshot_ref: "snap_1" },
        { promotion_id: "p2", hypothesis_id: "h2", realization_id: null, decision: "declined", decided_at: "2026-07-23T00:00:00Z", reviewer: "bob", rationale: "insufficient sample size", evidence_snapshot_ref: "snap_1" },
      ],
    });
    const result = await fetchPromotionHistory();
    expect(result.records).toHaveLength(2);
    expect(result.records[0].realization_id).toBe("r1");
    expect(result.records[0].rationale).toBe("strong out-of-sample edge");
    expect(result.records[1].realization_id).toBeNull();
  });

  it("parses an empty history (200, not an error)", async () => {
    mockFetchOnce({ ok: true, records: [] });
    const result = await fetchPromotionHistory();
    expect(result.records).toEqual([]);
  });

  it("rejects an unrecognized decision value", async () => {
    mockFetchOnce({
      ok: true,
      records: [{ promotion_id: "p1", hypothesis_id: "h1", realization_id: null, decision: "maybe", decided_at: "2026-07-23T00:00:00Z" }],
    });
    await expect(fetchPromotionHistory()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("rejects a record missing decided_at", async () => {
    mockFetchOnce({
      ok: true,
      records: [{ promotion_id: "p1", hypothesis_id: "h1", realization_id: null, decision: "approved" }],
    });
    await expect(fetchPromotionHistory()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("throws upstream_error when the Ledger is degraded (503)", async () => {
    mockFetchOnce({ ok: false, error: "research ledger storage is degraded: not_configured" }, 503);
    await expect(fetchPromotionHistory()).rejects.toMatchObject({ kind: "upstream_error" });
  });
});

describe("fetchLineage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function lineageBody(overrides: Record<string, unknown> = {}) {
    return {
      ok: true,
      hypothesis_id: "h1",
      realization_id: "r1",
      promotion_records: [],
      validation_results: [
        { validation_id: "v1", hypothesis_id: "h1", verdict: "supported", justification: "ok", validated_at: "2026-07-23T00:00:00Z", out_of_sample: true },
      ],
      evidence: [{ evidence_id: "e1", experiment_id: "exp1", computed_at: "2026-07-23T00:00:00Z", metrics: { sharpe: 1.2 } }],
      experiments: [{ experiment_id: "exp1", hypothesis_id: "h1", executed_at: "2026-07-23T00:00:00Z", code_version: "abc123", passed: true }],
      realization: { realization_id: "r1", hypothesis_id: "h1", kind: "parameter_grid", version: "1", parameters: {}, status: "active", created_at: "2026-07-23T00:00:00Z" },
      warnings: [],
      ...overrides,
    };
  }

  it("parses a full lineage chain keyed by validation_id", async () => {
    mockFetchOnce(lineageBody());
    const result = await fetchLineage({ validationId: "v1" });
    expect(result.hypothesis_id).toBe("h1");
    expect(result.realization).not.toBeNull();
    expect(result.experiments).toHaveLength(1);
    expect(result.validation_results[0].verdict).toBe("supported");
  });

  it("parses a lineage response with a null realization and empty arrays", async () => {
    mockFetchOnce(lineageBody({ realization_id: null, realization: null, validation_results: [], evidence: [], experiments: [] }));
    const result = await fetchLineage({ validationId: "v1" });
    expect(result.realization).toBeNull();
    expect(result.experiments).toEqual([]);
  });

  it("parses non-empty warnings for a Ledger integrity gap", async () => {
    mockFetchOnce(lineageBody({ warnings: ["evidence 'e2' referenced by validation result 'v1' but not found in the Ledger"] }));
    const result = await fetchLineage({ validationId: "v1" });
    expect(result.warnings).toHaveLength(1);
  });

  it("throws not_found when no validation result exists for the given id (404)", async () => {
    mockFetchOnce({ ok: false, error: "no validation result with id 'v9'" }, 404);
    await expect(fetchLineage({ validationId: "v9" })).rejects.toMatchObject({ kind: "not_found" });
  });

  it("throws upstream_error when the Ledger is degraded (503)", async () => {
    mockFetchOnce({ ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" }, 503);
    await expect(fetchLineage({ validationId: "v1" })).rejects.toMatchObject({ kind: "upstream_error" });
  });

  it("rejects an unrecognized verdict value", async () => {
    mockFetchOnce(lineageBody({ validation_results: [{ validation_id: "v1", hypothesis_id: "h1", verdict: "maybe", justification: "x", validated_at: "2026-07-23T00:00:00Z", out_of_sample: false }] }));
    await expect(fetchLineage({ validationId: "v1" })).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

function promotionRecordFixture(overrides: Partial<PromotionRecordSummary> = {}): PromotionRecordSummary {
  return {
    promotion_id: "p1",
    hypothesis_id: "h1",
    realization_id: "r1",
    decision: "approved",
    decided_at: "2026-07-23T00:00:00Z",
    reviewer: "alice",
    rationale: "test rationale",
    evidence_snapshot_ref: "snap_1",
    ...overrides,
  };
}

describe("deriveEntryPromotionStatus", () => {
  const entry = { hypothesis_id: "h1", realization_id: "r1" };

  it("returns pending when no promotion record matches", () => {
    expect(deriveEntryPromotionStatus(entry, [])).toBe("pending");
  });

  it("returns the decision when exactly one record matches the (hypothesis_id, realization_id) pair", () => {
    const promotions = [promotionRecordFixture({ decision: "declined" })];
    expect(deriveEntryPromotionStatus(entry, promotions)).toBe("declined");
  });

  it("never matches on hypothesis_id alone - a different realization_id is not a match", () => {
    const promotions = [promotionRecordFixture({ realization_id: "r2", decision: "approved" })];
    expect(deriveEntryPromotionStatus(entry, promotions)).toBe("pending");
  });

  it("matches null realization_id correctly for decision-free hypotheses", () => {
    const decisionFreeEntry = { hypothesis_id: "h1", realization_id: null };
    const promotions = [promotionRecordFixture({ realization_id: null, decision: "approved" })];
    expect(deriveEntryPromotionStatus(decisionFreeEntry, promotions)).toBe("approved");
  });

  it("returns the most recent decision by decided_at when multiple records match the same pair", () => {
    const promotions = [
      promotionRecordFixture({ promotion_id: "p1", decision: "declined", decided_at: "2026-07-20T00:00:00Z" }),
      promotionRecordFixture({ promotion_id: "p2", decision: "approved", decided_at: "2026-07-23T00:00:00Z" }),
    ];
    expect(deriveEntryPromotionStatus(entry, promotions)).toBe("approved");
  });
});

describe("fetchPromotionCandidates", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses a non-empty candidate list, including a fresh candidate with no prior decisions", async () => {
    mockFetchOnce({
      ok: true,
      snapshot_id: "snap_1",
      candidates: [
        { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1", prior_decisions: [] },
      ],
    });
    const result = await fetchPromotionCandidates();
    expect(result.snapshot_id).toBe("snap_1");
    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0].prior_decisions).toEqual([]);
  });

  it("parses a candidate being reconsidered, with a non-empty prior_decisions", async () => {
    mockFetchOnce({
      ok: true,
      snapshot_id: "snap_1",
      candidates: [
        {
          hypothesis_id: "h1",
          realization_id: "r1",
          rank: 1,
          score: 1.0,
          validation_id: "v1",
          prior_decisions: [
            { promotion_id: "p1", hypothesis_id: "h1", realization_id: "r1", decision: "deferred", decided_at: "2026-07-23T00:00:00Z", reviewer: "alice", rationale: "needs more data", evidence_snapshot_ref: "snap_0" },
          ],
        },
      ],
    });
    const result = await fetchPromotionCandidates();
    expect(result.candidates[0].prior_decisions).toHaveLength(1);
    expect(result.candidates[0].prior_decisions[0].decision).toBe("deferred");
  });

  it("parses no-snapshot-yet as a normal 200 (snapshot_id null, empty candidates), not an error", async () => {
    mockFetchOnce({ ok: true, snapshot_id: null, candidates: [] });
    const result = await fetchPromotionCandidates();
    expect(result.snapshot_id).toBeNull();
    expect(result.candidates).toEqual([]);
  });

  it("throws upstream_error when the Ledger is degraded (503)", async () => {
    mockFetchOnce({ ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" }, 503);
    await expect(fetchPromotionCandidates()).rejects.toMatchObject({ kind: "upstream_error" });
  });

  it("rejects a candidate whose prior_decisions entry is missing a required field", async () => {
    mockFetchOnce({
      ok: true,
      snapshot_id: "snap_1",
      candidates: [
        { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1", prior_decisions: [{ promotion_id: "p1", hypothesis_id: "h1" }] },
      ],
    });
    await expect(fetchPromotionCandidates()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("deriveCandidateStatus", () => {
  it("returns pending for a fresh candidate with no prior decisions", () => {
    expect(deriveCandidateStatus({ prior_decisions: [] })).toBe("pending");
  });

  it("returns the single prior decision's own value for a candidate being reconsidered", () => {
    expect(deriveCandidateStatus({ prior_decisions: [promotionRecordFixture({ decision: "deferred" })] })).toBe("deferred");
  });

  it("returns the most recent prior decision by decided_at when more than one exists", () => {
    const priorDecisions: PromotionRecordSummary[] = [
      promotionRecordFixture({ promotion_id: "p1", decision: "declined", decided_at: "2026-07-20T00:00:00Z" }),
      promotionRecordFixture({ promotion_id: "p2", decision: "deferred", decided_at: "2026-07-23T00:00:00Z" }),
    ];
    expect(deriveCandidateStatus({ prior_decisions: priorDecisions })).toBe("deferred");
  });
});

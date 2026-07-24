// Sprint 10 Slice B. Typed client for the Research Overview page - GET
// /status, GET /research/leaderboard (latest snapshot only, no
// snapshot_id - Slice C's Snapshot selector adds that), GET
// /research/promotion (full history, no promotion_id - Slice E's own
// scope), all reached through the same-origin BFF proxy exactly like
// researchApi.ts's own RE-1/RE-2/dataset-health clients.
//
// Deliberately a separate module from researchApi.ts, not an extension of
// it: researchApi.ts is scoped to the frozen RE-1/RE-2 statistical
// baseline (source_track: "live"|"frozen", ResponseEnvelope) - a
// completely different backend subsystem (atlas.research_export) from the
// Research Ledger (atlas.research_deploy/atlas.research.promotion) this
// file reads. Ledger/Promotion responses carry no ResponseEnvelope at all
// (they're permanent facts, not live-vs-frozen dual-track data) - see the
// Sprint 10 architecture review §1 for why conflating the two would be a
// real modeling mistake, not just a style choice.
//
// GET /status is read through the same secure proxy boundary.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

// --- GET /status (research_ledger + database fields only - this page's
//     concern; tradingview/pickmytrade/claude are the legacy Connection
//     Status panel's own fields, untouched and untyped here) -------------

export interface LedgerCheckResult {
  ok: boolean;
  reason: string | null;
  detail: string | null;
}

export interface ResearchLedgerReadiness {
  status: "ready" | "degraded";
  reason: string | null;
  checks: Record<string, LedgerCheckResult>;
}

export interface OpsStatusResponse {
  database: { ok: boolean; reason: string | null; detail: string };
  research_ledger: ResearchLedgerReadiness;
}

function isLedgerCheckResult(value: unknown): value is LedgerCheckResult {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.ok === "boolean" &&
    (v.reason === null || typeof v.reason === "string") &&
    (v.detail === null || typeof v.detail === "string")
  );
}

function isResearchLedgerReadiness(value: unknown): value is ResearchLedgerReadiness {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    (v.status === "ready" || v.status === "degraded") &&
    (v.reason === null || typeof v.reason === "string") &&
    typeof v.checks === "object" &&
    v.checks !== null &&
    Object.values(v.checks as Record<string, unknown>).every(isLedgerCheckResult)
  );
}

function isOpsStatusResponse(value: unknown): value is OpsStatusResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (typeof v.database !== "object" || v.database === null) return false;
  const database = v.database as Record<string, unknown>;
  return (
    typeof database.ok === "boolean" &&
    (database.reason === null || typeof database.reason === "string") &&
    typeof database.detail === "string" &&
    isResearchLedgerReadiness(v.research_ledger)
  );
}

export function fetchOpsStatus(): Promise<OpsStatusResponse> {
  return proxyGet("status", {}, isOpsStatusResponse);
}

// --- GET /research/leaderboard (latest snapshot) -------------------------

export interface LeaderboardEntrySummary {
  hypothesis_id: string;
  realization_id: string | null;
  rank: number;
  score: number;
  validation_id: string | null;
}

export interface LatestSnapshotResponse {
  ok: true;
  snapshot_id: string;
  created_at: string;
  ranking_policy_id: string | null;
  ranking_policy_version: string | null;
  entries: LeaderboardEntrySummary[];
}

function isLeaderboardEntrySummary(value: unknown): value is LeaderboardEntrySummary {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.hypothesis_id === "string" &&
    (v.realization_id === null || typeof v.realization_id === "string") &&
    typeof v.rank === "number" &&
    typeof v.score === "number" &&
    (v.validation_id === null || typeof v.validation_id === "string")
  );
}

function isLatestSnapshotResponse(value: unknown): value is LatestSnapshotResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.ok === true &&
    typeof v.snapshot_id === "string" &&
    typeof v.created_at === "string" &&
    (v.ranking_policy_id === null || typeof v.ranking_policy_id === "string") &&
    (v.ranking_policy_version === null || typeof v.ranking_policy_version === "string") &&
    Array.isArray(v.entries) &&
    v.entries.every(isLeaderboardEntrySummary)
  );
}

/** No snapshot recorded yet is a real, expected state (backend 404,
 * "no leaderboard snapshots have been recorded yet") - callers distinguish
 * it via `error.kind === "not_found"` (ApiFetchError, re-exported above),
 * never treating it the same as an actual failure. */
export function fetchLatestSnapshot(): Promise<LatestSnapshotResponse> {
  return proxyGet("research/leaderboard", {}, isLatestSnapshotResponse);
}

// --- GET /research/promotion (full history) -------------------------------

export type PromotionDecisionValue = "approved" | "declined" | "deferred";

export interface PromotionRecordSummary {
  promotion_id: string;
  hypothesis_id: string;
  // Sprint 10 Slice C: realization_id/decided_at added (the backend already
  // returned both - Slice B simply didn't type or read them yet, since it
  // only needed a total count). Both are required for
  // deriveEntryPromotionStatus() below to match a promotion record against
  // a leaderboard entry the same, unambiguous way the backend itself always
  // does: the (hypothesis_id, realization_id) pair, never hypothesis_id
  // alone (see the Sprint 9 realization lineage correction) - and, when
  // more than one decision exists for that same pair, the most recent one
  // by decided_at.
  realization_id: string | null;
  decision: PromotionDecisionValue;
  decided_at: string;
  // Sprint 10 Slice E: reviewer/rationale/evidence_snapshot_ref added (the
  // backend already returned all three unchanged since Sprint 9 - Slice C
  // simply didn't type or read them yet, since the Leaderboard page only
  // needed decision status). All three are non-optional on the wire:
  // PromotionRecord.__post_init__ rejects a blank rationale or reviewer at
  // write time, and evidence_snapshot_ref is a required constructor field -
  // there is no PromotionRecord in the Ledger without them.
  reviewer: string;
  rationale: string;
  evidence_snapshot_ref: string;
}

export interface PromotionHistoryResponse {
  ok: true;
  records: PromotionRecordSummary[];
}

function isPromotionDecisionValue(value: unknown): value is PromotionDecisionValue {
  return value === "approved" || value === "declined" || value === "deferred";
}

function isPromotionRecordSummary(value: unknown): value is PromotionRecordSummary {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.promotion_id === "string" &&
    typeof v.hypothesis_id === "string" &&
    (v.realization_id === null || typeof v.realization_id === "string") &&
    isPromotionDecisionValue(v.decision) &&
    typeof v.decided_at === "string" &&
    typeof v.reviewer === "string" &&
    typeof v.rationale === "string" &&
    typeof v.evidence_snapshot_ref === "string"
  );
}

function isPromotionHistoryResponse(value: unknown): value is PromotionHistoryResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return v.ok === true && Array.isArray(v.records) && v.records.every(isPromotionRecordSummary);
}

/** Zero promotions recorded yet is a normal 200 with an empty array (unlike
 * the leaderboard's 404-for-empty) - callers check `records.length === 0`
 * directly, no error kind involved. */
export function fetchPromotionHistory(): Promise<PromotionHistoryResponse> {
  return proxyGet("research/promotion", {}, isPromotionHistoryResponse);
}

// --- Sprint 10 Slice C: leaderboard entry <-> promotion status join --------
// Pure, client-side, no new endpoint - both arrays are already fetched for
// the Leaderboard page's own summary strip / promotion count. Never joins
// on hypothesis_id alone.

export type EntryPromotionStatus = PromotionDecisionValue | "pending";

export function deriveEntryPromotionStatus(
  entry: Pick<LeaderboardEntrySummary, "hypothesis_id" | "realization_id">,
  promotions: readonly PromotionRecordSummary[],
): EntryPromotionStatus {
  const matches = promotions.filter(
    (p) => p.hypothesis_id === entry.hypothesis_id && p.realization_id === entry.realization_id,
  );
  if (matches.length === 0) return "pending";
  const latest = matches.reduce((a, b) => (a.decided_at > b.decided_at ? a : b));
  return latest.decision;
}

// --- GET /research/promotion/candidates (Sprint 10 Slice E) ----------------
// Typed client for atlas/api/v1/promotion.py's read_promotion_candidates -
// built in Sprint 9, deliberately left unconsumed by any typed client
// until now (this is the first page that needs it). Reuses the backend's
// own list_promotion_candidates() semantics unchanged: candidates already
// exclude anything with an APPROVED PromotionRecord for its own
// (hypothesis_id, realization_id) pair - "nothing left to decide" - so
// this endpoint's own response IS the queue, no client-side filtering
// needed. A candidate with a non-empty prior_decisions (DECLINED/DEFERRED
// only, by the backend's own construction) is being reconsidered, not
// seen for the first time - deriveCandidateStatus() below surfaces that
// distinction the same way Slice C's deriveEntryPromotionStatus() does for
// the Leaderboard, over data this endpoint already embeds per-candidate
// rather than requiring a second query.

export interface PromotionCandidateSummary {
  hypothesis_id: string;
  realization_id: string | null;
  rank: number;
  score: number;
  validation_id: string | null;
  prior_decisions: PromotionRecordSummary[];
}

export interface PromotionCandidatesResponse {
  ok: true;
  snapshot_id: string | null;
  candidates: PromotionCandidateSummary[];
}

function isPromotionCandidateSummary(value: unknown): value is PromotionCandidateSummary {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.hypothesis_id === "string" &&
    (v.realization_id === null || typeof v.realization_id === "string") &&
    typeof v.rank === "number" &&
    typeof v.score === "number" &&
    (v.validation_id === null || typeof v.validation_id === "string") &&
    Array.isArray(v.prior_decisions) &&
    v.prior_decisions.every(isPromotionRecordSummary)
  );
}

function isPromotionCandidatesResponse(value: unknown): value is PromotionCandidatesResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.ok === true &&
    (v.snapshot_id === null || typeof v.snapshot_id === "string") &&
    Array.isArray(v.candidates) &&
    v.candidates.every(isPromotionCandidateSummary)
  );
}

/** No current snapshot at all is a normal 200 (`snapshot_id: null,
 * candidates: []`), not an error - mirrors this endpoint's own router
 * behavior, never a 404. */
export function fetchPromotionCandidates(): Promise<PromotionCandidatesResponse> {
  return proxyGet("research/promotion/candidates", {}, isPromotionCandidatesResponse);
}

/** A fresh candidate (no prior_decisions) is "pending"; one carrying a
 * prior DECLINED/DEFERRED decision is being reconsidered - surfaced as
 * that decision's own value, picking the most recent by decided_at when
 * more than one exists. Never "approved": list_promotion_candidates()
 * already excludes any candidate with an APPROVED record for its own
 * (hypothesis_id, realization_id) pair, by construction. */
export function deriveCandidateStatus(candidate: Pick<PromotionCandidateSummary, "prior_decisions">): EntryPromotionStatus {
  if (candidate.prior_decisions.length === 0) return "pending";
  const latest = candidate.prior_decisions.reduce((a, b) => (a.decided_at > b.decided_at ? a : b));
  return latest.decision;
}

// --- GET /research/lineage (Sprint 10 Slice D) -----------------------------
// Typed client for atlas/api/v1/research_lineage.py's composed, read-only
// walk - built in Slice A, deliberately left unconsumed by any typed
// client until now (Slice D is the first page that needs it). Every field
// below is verified against serialization.py directly, not assumed - each
// interface types only the fields this page actually renders, per the
// Snapshot Explorer's own "avoid information overload" mandate; fields
// that exist on the wire but aren't needed here (fingerprints, full
// dataset manifests, criteria_results detail, leaderboard_entries,
// requested_promotion_id/requested_validation_id) are simply never
// declared - TypeScript's structural typing doesn't require modeling a
// field just because the backend sends it.
//
// One deliberate, disclosed gap: this endpoint never returns the
// Hypothesis entity itself (statement/author/dataset), only
// hypothesis_id. That's not an oversight here - atlas.research.stores.
// HypothesisRegistry is never actually written to by the real pipeline
// (a pre-existing gap disclosed during the Sprint 9 realization lineage
// correction), so even if research_lineage.py were extended to look one
// up, it would return null for any hypothesis the current pipeline
// actually produces. Extending the backend to fetch something that isn't
// there yet isn't "absolutely necessary" - it would be dead code. The
// Hypothesis node below is identified by hypothesis_id alone until the
// pipeline itself persists Hypotheses, which is out of this slice's scope
// entirely.

export type LineageVerdict = "supported" | "not_supported" | "inconclusive";

export interface LineagePromotionRecord {
  promotion_id: string;
  hypothesis_id: string;
  realization_id: string | null;
  decision: PromotionDecisionValue;
  reviewer: string;
  rationale: string;
  decided_at: string;
}

export interface LineageRealization {
  realization_id: string;
  hypothesis_id: string;
  kind: string;
  version: string;
  parameters: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface LineageExperiment {
  experiment_id: string;
  hypothesis_id: string;
  executed_at: string;
  code_version: string | null;
  passed: boolean;
}

export interface LineageEvidence {
  evidence_id: string;
  experiment_id: string;
  computed_at: string;
  metrics: Record<string, unknown>;
}

export interface LineageValidationResult {
  validation_id: string;
  hypothesis_id: string;
  verdict: LineageVerdict;
  justification: string;
  validated_at: string;
  out_of_sample: boolean;
}

export interface LineageResponse {
  ok: true;
  hypothesis_id: string;
  realization_id: string | null;
  promotion_records: LineagePromotionRecord[];
  validation_results: LineageValidationResult[];
  evidence: LineageEvidence[];
  experiments: LineageExperiment[];
  realization: LineageRealization | null;
  warnings: string[];
}

function isLineageVerdict(value: unknown): value is LineageVerdict {
  return value === "supported" || value === "not_supported" || value === "inconclusive";
}

function isLineagePromotionRecord(value: unknown): value is LineagePromotionRecord {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.promotion_id === "string" &&
    typeof v.hypothesis_id === "string" &&
    (v.realization_id === null || typeof v.realization_id === "string") &&
    isPromotionDecisionValue(v.decision) &&
    typeof v.reviewer === "string" &&
    typeof v.rationale === "string" &&
    typeof v.decided_at === "string"
  );
}

function isLineageRealization(value: unknown): value is LineageRealization {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.realization_id === "string" &&
    typeof v.hypothesis_id === "string" &&
    typeof v.kind === "string" &&
    typeof v.version === "string" &&
    typeof v.parameters === "object" &&
    v.parameters !== null &&
    typeof v.status === "string" &&
    typeof v.created_at === "string"
  );
}

function isLineageExperiment(value: unknown): value is LineageExperiment {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.experiment_id === "string" &&
    typeof v.hypothesis_id === "string" &&
    typeof v.executed_at === "string" &&
    (v.code_version === null || typeof v.code_version === "string") &&
    typeof v.passed === "boolean"
  );
}

function isLineageEvidence(value: unknown): value is LineageEvidence {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.evidence_id === "string" &&
    typeof v.experiment_id === "string" &&
    typeof v.computed_at === "string" &&
    typeof v.metrics === "object" &&
    v.metrics !== null
  );
}

function isLineageValidationResult(value: unknown): value is LineageValidationResult {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.validation_id === "string" &&
    typeof v.hypothesis_id === "string" &&
    isLineageVerdict(v.verdict) &&
    typeof v.justification === "string" &&
    typeof v.validated_at === "string" &&
    typeof v.out_of_sample === "boolean"
  );
}

function isLineageResponse(value: unknown): value is LineageResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.ok === true &&
    typeof v.hypothesis_id === "string" &&
    (v.realization_id === null || typeof v.realization_id === "string") &&
    Array.isArray(v.promotion_records) &&
    v.promotion_records.every(isLineagePromotionRecord) &&
    Array.isArray(v.validation_results) &&
    v.validation_results.every(isLineageValidationResult) &&
    Array.isArray(v.evidence) &&
    v.evidence.every(isLineageEvidence) &&
    Array.isArray(v.experiments) &&
    v.experiments.every(isLineageExperiment) &&
    (v.realization === null || isLineageRealization(v.realization)) &&
    Array.isArray(v.warnings) &&
    v.warnings.every((w) => typeof w === "string")
  );
}

/** Exactly one of promotionId/validationId must be given - matches the
 * backend's own "exactly one of promotion_id or validation_id" contract.
 * The Snapshot Explorer always calls this with validationId (from the
 * selected leaderboard entry) - promotionId support exists here because
 * the backend endpoint itself supports it, not because this slice's page
 * uses it. */
export function fetchLineage(params: { promotionId: string } | { validationId: string }): Promise<LineageResponse> {
  const query: Record<string, string> =
    "promotionId" in params ? { promotion_id: params.promotionId } : { validation_id: params.validationId };
  return proxyGet("research/lineage", query, isLineageResponse);
}

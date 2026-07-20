// UI v2. Typed client for GET /research/re1/summary, /research/re2/summary,
// and /research/dataset-health, all reached through the same-origin BFF
// proxy. RE-1/RE-2 report bodies are large, free-form payloads produced by
// atlas/research_export/snapshot_builder.py from the frozen statistical/
// setup-profiling packages - left as `unknown` here and narrowed by the
// Research Overview page itself (a later commit) rather than duplicating
// their full nested shape into this client speculatively. Dataset Health's
// payload IS fully typed below since its shape is small, stable, and
// consumed by more than one component (DatasetHealthPage, FreshnessBadge,
// MismatchBanner).

import { ResponseEnvelope, isResponseEnvelope } from "@/lib/apiEnvelope";
import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

// --- GET /research/re1/summary, /research/re2/summary ----------------------

export interface ResearchSummaryResponse {
  ok: true;
  envelope: ResponseEnvelope;
  report: unknown;
}

function isResearchSummaryResponse(value: unknown): value is ResearchSummaryResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return v.ok === true && isResponseEnvelope(v.envelope) && "report" in v;
}

export function fetchRe1Summary(): Promise<ResearchSummaryResponse> {
  return proxyGet("research/re1/summary", {}, isResearchSummaryResponse);
}

export function fetchRe2Summary(): Promise<ResearchSummaryResponse> {
  return proxyGet("research/re2/summary", {}, isResearchSummaryResponse);
}

// --- RE-2 report: setup_profile.entries[] duration distributions -----------
// The one slice of RE-2's otherwise-`unknown` report Episode Inspector needs
// (architecture §3.3) - narrowed here, on demand, rather than typing the
// whole report speculatively (see this file's header comment).

export interface DurationDistribution {
  count: number;
  max: number;
  mean: number;
  median: number;
  p75: number;
  p90: number;
  p95: number;
}

export interface SetupProfileEntry {
  setup_name: string;
  episode_count: number;
  all_episodes_duration: DurationDistribution;
  fully_observed_duration: DurationDistribution;
}

function isDurationDistribution(value: unknown): value is DurationDistribution {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.count === "number" &&
    typeof v.max === "number" &&
    typeof v.mean === "number" &&
    typeof v.median === "number" &&
    typeof v.p75 === "number" &&
    typeof v.p90 === "number" &&
    typeof v.p95 === "number"
  );
}

function isSetupProfileEntry(value: unknown): value is SetupProfileEntry {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.setup_name === "string" &&
    typeof v.episode_count === "number" &&
    isDurationDistribution(v.all_episodes_duration) &&
    isDurationDistribution(v.fully_observed_duration)
  );
}

// Returns null (never throws) on any unexpected shape - a malformed frozen
// report should degrade Episode Inspector's historical panel gracefully,
// not crash the page.
export function findSetupProfileEntry(report: unknown, setupName: string): SetupProfileEntry | null {
  if (typeof report !== "object" || report === null) return null;
  const setupProfile = (report as Record<string, unknown>).setup_profile;
  if (typeof setupProfile !== "object" || setupProfile === null) return null;
  const entries = (setupProfile as Record<string, unknown>).entries;
  if (!Array.isArray(entries)) return null;
  const match = entries.find((e) => isSetupProfileEntry(e) && e.setup_name === setupName);
  return match && isSetupProfileEntry(match) ? match : null;
}

// --- GET /research/dataset-health -------------------------------------------

export interface DateRange {
  start: string;
  end: string;
}

export interface DatasetIdentity {
  symbol: string;
  timeframe: string;
  row_count: number;
  date_range: DateRange;
}

// Per-check verdict (scripts/certify_historical_dataset.py's own PASS/WARNING/FAIL
// constants) - a DIFFERENT domain from the summary's own aggregate verdict below.
export type CertificationCheckVerdict = "PASS" | "WARNING" | "FAIL";

export interface CertificationCheckResult {
  section: string;
  check: string;
  verdict: CertificationCheckVerdict;
  detail: string;
}

// The summary's aggregate verdict (atlas/research_export/snapshot_builder.py) -
// "rejected" whenever any check FAILs, "certified_with_warnings" when only
// WARNINGs remain, "certified" only when every check PASSes. Not the same
// three values as an individual check's own verdict above.
export type CertificationOverallVerdict = "certified" | "certified_with_warnings" | "rejected";

export interface CertificationSummary {
  checks_run: number;
  pass_count: number;
  warning_count: number;
  fail_count: number;
  verdict: CertificationOverallVerdict;
  checks: CertificationCheckResult[];
}

export type KnownWarningSeverity = "warning" | "fail";

// One manually-curated, typed, traceable disclosed limitation of the frozen
// baseline (amendment 8) - source_document/source_section must remain
// visible or accessible in the UI per the approved requirements, never
// dropped even when only title/detail are shown inline.
export interface KnownWarning {
  id: string;
  severity: KnownWarningSeverity;
  title: string;
  detail: string;
  source_document: string;
  source_section: string;
}

export interface FrozenVersion {
  source_computation_version: string | null;
  exported_at: string;
}

export interface DatasetHealthResponse {
  ok: true;
  envelope: ResponseEnvelope;
  dataset_identity: DatasetIdentity;
  segment_count: number;
  certification: CertificationSummary;
  known_warnings: KnownWarning[];
  frozen_version: FrozenVersion;
}

function isDateRange(value: unknown): value is DateRange {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.start === "string" && typeof v.end === "string";
}

function isDatasetIdentity(value: unknown): value is DatasetIdentity {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.symbol === "string" &&
    typeof v.timeframe === "string" &&
    typeof v.row_count === "number" &&
    isDateRange(v.date_range)
  );
}

function isCertificationCheckResult(value: unknown): value is CertificationCheckResult {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.section === "string" &&
    typeof v.check === "string" &&
    typeof v.verdict === "string" &&
    typeof v.detail === "string"
  );
}

function isCertificationSummary(value: unknown): value is CertificationSummary {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.checks_run === "number" &&
    typeof v.pass_count === "number" &&
    typeof v.warning_count === "number" &&
    typeof v.fail_count === "number" &&
    typeof v.verdict === "string" &&
    Array.isArray(v.checks) &&
    v.checks.every(isCertificationCheckResult)
  );
}

function isKnownWarning(value: unknown): value is KnownWarning {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "string" &&
    (v.severity === "warning" || v.severity === "fail") &&
    typeof v.title === "string" &&
    typeof v.detail === "string" &&
    typeof v.source_document === "string" &&
    typeof v.source_section === "string"
  );
}

function isFrozenVersion(value: unknown): value is FrozenVersion {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    (v.source_computation_version === null || typeof v.source_computation_version === "string") &&
    typeof v.exported_at === "string"
  );
}

function isDatasetHealthResponse(value: unknown): value is DatasetHealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.ok === true &&
    isResponseEnvelope(v.envelope) &&
    isDatasetIdentity(v.dataset_identity) &&
    typeof v.segment_count === "number" &&
    isCertificationSummary(v.certification) &&
    Array.isArray(v.known_warnings) &&
    v.known_warnings.every(isKnownWarning) &&
    isFrozenVersion(v.frozen_version)
  );
}

export function fetchDatasetHealth(): Promise<DatasetHealthResponse> {
  return proxyGet("research/dataset-health", {}, isDatasetHealthResponse);
}

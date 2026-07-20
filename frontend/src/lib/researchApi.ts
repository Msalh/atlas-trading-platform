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

export type CertificationVerdict = "PASS" | "WARNING" | "FAIL";

export interface CertificationCheckResult {
  section: string;
  check: string;
  verdict: CertificationVerdict;
  detail: string;
}

export interface CertificationSummary {
  checks_run: number;
  pass_count: number;
  warning_count: number;
  fail_count: number;
  verdict: CertificationVerdict;
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

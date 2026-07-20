// UI v2. Typed client for GET /setup-engine/latest and
// GET /setup-engine/episodes/live, both reached through the same-origin BFF
// proxy (src/app/api/proxy/[...path]/route.ts). Mirrors the wire shapes
// hand-built by atlas/api/v1/setup_engine.py, atlas/setup_engine/service.py
// (setup_engine_output_to_dict), and atlas/live_view/models.py - keep in
// sync if those change.

import { ResponseEnvelope, isResponseEnvelope } from "@/lib/apiEnvelope";
import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

// --- GET /setup-engine/latest ----------------------------------------------

export type SetupSeverity = "weak" | "normal" | "strong";

export interface SupportingFact {
  fact_name: string;
  occurred_at: string;
  value: unknown;
  detail: Record<string, unknown>;
}

export interface ComputedSetup {
  name: string;
  status: "computed";
  detected: boolean;
  severity: SetupSeverity | null;
  definition_version: string;
  evidence: { supporting_facts: SupportingFact[] };
}

export interface InsufficientDataSetup {
  name: string;
  status: "insufficient_data";
  definition_version: string;
  reason: string;
}

export type Setup = ComputedSetup | InsufficientDataSetup;

export interface SetupEngineOutput {
  schema_version: string;
  symbol: string;
  timeframe: string;
  occurred_at: string;
  setups: Setup[];
}

export interface SetupEngineLatestResponse {
  ok: true;
  found: boolean;
  envelope?: ResponseEnvelope; // absent when found=false - nothing ingested yet
  data: SetupEngineOutput | null;
}

function isSetup(value: unknown): value is Setup {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (typeof v.name !== "string" || typeof v.definition_version !== "string") return false;
  if (v.status === "computed") {
    return (
      typeof v.detected === "boolean" &&
      (v.severity === null || typeof v.severity === "string") &&
      typeof v.evidence === "object" &&
      v.evidence !== null &&
      Array.isArray((v.evidence as Record<string, unknown>).supporting_facts)
    );
  }
  if (v.status === "insufficient_data") {
    return typeof v.reason === "string";
  }
  return false;
}

function isSetupEngineOutput(value: unknown): value is SetupEngineOutput {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.schema_version === "string" &&
    typeof v.symbol === "string" &&
    typeof v.timeframe === "string" &&
    typeof v.occurred_at === "string" &&
    Array.isArray(v.setups) &&
    v.setups.every(isSetup)
  );
}

function isSetupEngineLatestResponse(value: unknown): value is SetupEngineLatestResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (v.ok !== true || typeof v.found !== "boolean") return false;
  if (!v.found) return v.data === null;
  return isSetupEngineOutput(v.data) && isResponseEnvelope(v.envelope);
}

export function fetchLatestSetupEngineOutput(symbol: string, timeframe: string): Promise<SetupEngineLatestResponse> {
  return proxyGet("setup-engine/latest", { symbol, timeframe }, isSetupEngineLatestResponse);
}

// --- GET /setup-engine/episodes/live ----------------------------------------

// Deliberately not RE-2's own TerminationReason - a live window has no
// dataset_end concept, and "still open" (is_active=true) is represented by
// termination_reason being entirely absent, never a fabricated enum member.
export type LeftBoundaryReason = "observed_activation" | "insufficient_data" | "segment_start" | "query_window_start";
export type LiveTerminationReason = "became_false" | "insufficient_data" | "segment_end";

// The 7 registered Rule Engine facts, captured at an episode's start/end bar.
// A null field means that fact was InsufficientData at that bar, never a
// fabricated value - never render null as false.
export interface RegisteredFactSnapshot {
  volume_spike: boolean | null;
  displacement: boolean | null;
  rejection: boolean | null;
  trend_5m: string | null;
  liquidity_sweep: boolean | null;
  reclaim: boolean | null;
  vwap_relationship: string | null;
}

export interface LiveEpisodeProjection {
  setup_name: string;
  segment_id: string;
  left_boundary_reason: LeftBoundaryReason;
  activation_timestamp_observed: string | null;
  observed_start_timestamp: string;
  duration_bars_observed: number;
  is_window_truncated: boolean;
  is_active: boolean;
  last_observed_timestamp: string;
  // Always null while is_active=true - never a real ending. See
  // architecture doc §4.2's UI rule.
  end_timestamp_observed: string | null;
  termination_reason: LiveTerminationReason | null;
  right_boundary_observed: boolean;
  is_continuation: boolean;
  start_state: RegisteredFactSnapshot;
  end_state: RegisteredFactSnapshot;
}

export interface LiveComputabilitySummary {
  computable_bars: number;
  non_computable_bars: number;
  detected_true_bars: number;
  detected_false_bars: number;
  insufficient_reason_counts: Record<string, number>;
}

export interface LiveSetupSnapshot {
  current_episode: LiveEpisodeProjection | null;
  recent_episodes: LiveEpisodeProjection[]; // always is_active=false
  computability: LiveComputabilitySummary;
}

export interface SegmentBoundary {
  segment_id: string;
  start_timestamp: string;
  end_timestamp: string | null; // null only for the window's own still-open segment
}

export interface LiveActivationEvent {
  timestamp: string;
  segment_id: string;
  activated_setups: string[]; // sorted alphabetically, no ordering implied
}

export interface LiveWindowData {
  window: { requested: number; actually_used: number };
  setups: Record<string, LiveSetupSnapshot>;
  segments: SegmentBoundary[];
  activation_events: LiveActivationEvent[];
}

export type LiveEpisodesResponse =
  | ({ ok: true; found: true; envelope: ResponseEnvelope } & LiveWindowData)
  | { ok: true; found: false; data: null };

function isRegisteredFactSnapshot(value: unknown): value is RegisteredFactSnapshot {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const bools: (keyof RegisteredFactSnapshot)[] = ["volume_spike", "displacement", "rejection", "liquidity_sweep", "reclaim"];
  const strs: (keyof RegisteredFactSnapshot)[] = ["trend_5m", "vwap_relationship"];
  return (
    bools.every((k) => v[k] === null || typeof v[k] === "boolean") &&
    strs.every((k) => v[k] === null || typeof v[k] === "string")
  );
}

function isLiveEpisodeProjection(value: unknown): value is LiveEpisodeProjection {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.setup_name === "string" &&
    typeof v.segment_id === "string" &&
    typeof v.left_boundary_reason === "string" &&
    (v.activation_timestamp_observed === null || typeof v.activation_timestamp_observed === "string") &&
    typeof v.observed_start_timestamp === "string" &&
    typeof v.duration_bars_observed === "number" &&
    typeof v.is_window_truncated === "boolean" &&
    typeof v.is_active === "boolean" &&
    typeof v.last_observed_timestamp === "string" &&
    (v.end_timestamp_observed === null || typeof v.end_timestamp_observed === "string") &&
    (v.termination_reason === null || typeof v.termination_reason === "string") &&
    typeof v.right_boundary_observed === "boolean" &&
    typeof v.is_continuation === "boolean" &&
    isRegisteredFactSnapshot(v.start_state) &&
    isRegisteredFactSnapshot(v.end_state)
  );
}

function isLiveComputabilitySummary(value: unknown): value is LiveComputabilitySummary {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.computable_bars === "number" &&
    typeof v.non_computable_bars === "number" &&
    typeof v.detected_true_bars === "number" &&
    typeof v.detected_false_bars === "number" &&
    typeof v.insufficient_reason_counts === "object" &&
    v.insufficient_reason_counts !== null
  );
}

function isLiveSetupSnapshot(value: unknown): value is LiveSetupSnapshot {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    (v.current_episode === null || isLiveEpisodeProjection(v.current_episode)) &&
    Array.isArray(v.recent_episodes) &&
    v.recent_episodes.every(isLiveEpisodeProjection) &&
    isLiveComputabilitySummary(v.computability)
  );
}

function isLiveWindowData(value: unknown): value is LiveWindowData {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (typeof v.window !== "object" || v.window === null) return false;
  const window = v.window as Record<string, unknown>;
  if (typeof window.requested !== "number" || typeof window.actually_used !== "number") return false;
  if (typeof v.setups !== "object" || v.setups === null) return false;
  if (!Object.values(v.setups as Record<string, unknown>).every(isLiveSetupSnapshot)) return false;
  if (!Array.isArray(v.segments)) return false;
  if (!Array.isArray(v.activation_events)) return false;
  return true;
}

function isLiveEpisodesResponse(value: unknown): value is LiveEpisodesResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (v.ok !== true || typeof v.found !== "boolean") return false;
  if (!v.found) return v.data === null;
  return isResponseEnvelope(v.envelope) && isLiveWindowData(v);
}

export function fetchLiveEpisodes(symbol: string, timeframe: string, window?: number): Promise<LiveEpisodesResponse> {
  const params: Record<string, string> = { symbol, timeframe };
  if (window !== undefined) params.window = String(window);
  return proxyGet("setup-engine/episodes/live", params, isLiveEpisodesResponse);
}

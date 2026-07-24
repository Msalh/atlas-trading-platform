// Typed client for GET /api/v1/rule-engine/latest through the same-origin BFF.

import { staleAfterMinutes } from "@/lib/freshness";
import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

// The backend's closed Timeframe enum (atlas/core/primitives.py). No metadata
// endpoint exists to fetch this list - Sprint 16 explicitly scoped that out.
// If the backend enum ever changes, this list must be updated by hand.
export const TIMEFRAMES = ["1m", "5m", "15m", "1h"] as const;
export type TimeframeValue = (typeof TIMEFRAMES)[number];

export type FactStatus = "computed" | "insufficient_data";

export interface ComputedFact {
  name: string;
  status: "computed";
  value: boolean | string;
  definition_version: string;
  evidence: Record<string, unknown>;
}

export interface InsufficientDataFact {
  name: string;
  status: "insufficient_data";
  definition_version: string;
  reason: string;
}

export type RuleEngineFact = ComputedFact | InsufficientDataFact;

export interface RuleEngineOutput {
  schema_version: string;
  symbol: string;
  timeframe: string;
  occurred_at: string;
  facts: RuleEngineFact[];
}

export interface RuleEngineLatestResponse {
  ok: boolean;
  found: boolean;
  data: RuleEngineOutput | null;
}

// Sprint 16's approved viewer heuristic - explicitly NOT the backend's
// configured staleness value (atlas/monitoring.py's own threshold is a
// separate, unrelated setting for a different purpose - alerting, not
// display). stale_after = max(3 * timeframe duration, 5 minutes) - now
// centralized in lib/freshness.ts (production-hardening amendment 5),
// which UI v2's own FreshnessBadge also uses, rather than each keeping
// its own copy of the same threshold table.
export function isStale(occurredAtIso: string, timeframe: string): boolean {
  const occurredAt = new Date(occurredAtIso).getTime();
  if (Number.isNaN(occurredAt)) return false;
  const ageMinutes = (Date.now() - occurredAt) / 60_000;
  return ageMinutes > staleAfterMinutes(timeframe);
}

// `/rule-engine/latest` is on the BFF proxy allowlist. Reuse this file's
// RuleEngineOutput/RuleEngineFact types rather than redefining them.

function isRuleEngineFact(value: unknown): value is RuleEngineFact {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (typeof v.name !== "string" || typeof v.definition_version !== "string") return false;
  if (v.status === "computed") {
    return typeof v.value === "boolean" || typeof v.value === "string";
  }
  if (v.status === "insufficient_data") {
    return typeof v.reason === "string";
  }
  return false;
}

function isRuleEngineOutput(value: unknown): value is RuleEngineOutput {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.schema_version === "string" &&
    typeof v.symbol === "string" &&
    typeof v.timeframe === "string" &&
    typeof v.occurred_at === "string" &&
    Array.isArray(v.facts) &&
    v.facts.every(isRuleEngineFact)
  );
}

function isRuleEngineLatestResponse(value: unknown): value is RuleEngineLatestResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (v.ok !== true || typeof v.found !== "boolean") return false;
  if (!v.found) return v.data === null;
  return isRuleEngineOutput(v.data);
}

export function fetchLatestRuleEngineOutputViaProxy(symbol: string, timeframe: string): Promise<RuleEngineLatestResponse> {
  return proxyGet("rule-engine/latest", { symbol, timeframe }, isRuleEngineLatestResponse);
}

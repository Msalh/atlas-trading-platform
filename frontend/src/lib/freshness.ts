// UI v2, production-hardening amendment 5. A reachable API with an old
// data_as_of must never continue displaying an unqualified LIVE badge -
// this module classifies data recency into an operational state, reused
// by FreshnessBadge everywhere it renders a LIVE envelope. Purely a
// freshness/UX classification of "how recent is this data" - no trading
// analytics, no signal, no recommendation, and it never itself decides
// what to render; callers (FreshnessBadge and its consumers) own that.
//
// "no_data" and "disconnected" are NOT computed here: they describe the
// query outcome BEFORE any envelope exists at all (found=false, or the
// fetch itself threw an ApiFetchError) - every UI v2 page already has a
// dedicated branch for each of those cases (a neutral "not ingested yet"
// message, or the inline {error.message} danger box), rendered instead
// of a FreshnessBadge, not alongside one. This module only classifies
// the remaining three states, which all require a real data_as_of to
// evaluate.

export type FreshnessState = "current" | "delayed" | "stale";

// Sprint 16's own per-timeframe bar-duration table
// (ruleEngineApi.ts::TIMEFRAME_DURATION_MINUTES), centralized here as the
// one source of truth - ruleEngineApi.ts's isStale now delegates to
// staleAfterMinutes() below instead of keeping its own copy.
export const TIMEFRAME_DURATION_MINUTES: Record<string, number> = {
  "1m": 1,
  "5m": 5,
  "15m": 15,
  "1h": 60,
};

function barDurationMinutes(timeframe: string): number {
  return TIMEFRAME_DURATION_MINUTES[timeframe] ?? 5;
}

// current -> delayed boundary: some slack past exactly one bar duration,
// so classification doesn't flip to "delayed" the instant a fresh bar is
// a few seconds later than the theoretical minimum - a fraction of the
// same bar-duration number below, not an independently invented number.
export function currentThresholdMinutes(timeframe: string): number {
  return barDurationMinutes(timeframe) * 1.5;
}

// delayed -> stale boundary: Sprint 16's own RuleEngineViewer stale_after
// heuristic (max(3x bar duration, 5 minutes)), reused verbatim here
// rather than reinvented.
export function staleAfterMinutes(timeframe: string): number {
  return Math.max(3 * barDurationMinutes(timeframe), 5);
}

/** dataAsOf must be a real, present ISO timestamp - callers only reach
 * this function once they already know data exists (found=true and the
 * fetch succeeded); the no_data/disconnected states are handled by the
 * caller's own separate branches, never by passing a null/missing value
 * in here. An unparseable timestamp is treated as "stale" defensively
 * (never as "current"), so a data bug can't accidentally imply freshness. */
export function classifyFreshness(dataAsOf: string, timeframe: string, now: number = Date.now()): FreshnessState {
  const ageMinutes = (now - new Date(dataAsOf).getTime()) / 60_000;
  if (Number.isNaN(ageMinutes) || ageMinutes < 0) return "stale";
  if (ageMinutes <= currentThresholdMinutes(timeframe)) return "current";
  if (ageMinutes <= staleAfterMinutes(timeframe)) return "delayed";
  return "stale";
}

// Client for GET /api/v1/rule-engine/latest (Sprint 15/16). Deliberately separate
// from src/lib/api.ts: that file's authHeaders() reads NEXT_PUBLIC_API_KEY, an
// env var shipped into the client bundle at build time. Sprint 16's approved
// design uses a MANUALLY entered key held only in component memory instead - a
// server-side proxy was explicitly deferred (see the Sprint 16 design notes),
// so this module never reads any API-key env var and never persists the key
// itself; the caller (RuleEngineViewer) is the only place the key value lives.

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

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

// Thrown (never returned as data) on any non-success outcome, so react-query's
// OWN native data/error separation does the "keep last good result visible
// across a failed refresh" work for us: react-query retains the last
// successful `data` even after a later refetch throws, while `error`/`isError`
// independently reflect the LATEST attempt. This replaced an earlier
// discriminated-result design that returned errors as "successful" data -
// that approach required hand-rolled state to recover the same behavior
// react-query already provides, and ran into this repo's lint rules against
// both setState-in-effect and ref access during render. `kind` lets the UI
// distinguish 401/422/network without parsing message text; `message` is
// always human-readable, non-secret detail text - never the API key.
export class RuleEngineFetchError extends Error {
  kind: "unauthorized" | "invalid" | "network_error";
  constructor(kind: "unauthorized" | "invalid" | "network_error", message: string) {
    super(message);
    this.name = "RuleEngineFetchError";
    this.kind = kind;
  }
}

export async function fetchLatestRuleEngineOutput(
  apiKey: string,
  symbol: string,
  timeframe: string,
): Promise<RuleEngineLatestResponse> {
  const qs = new URLSearchParams({ symbol, timeframe });
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/rule-engine/latest?${qs.toString()}`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${apiKey}` },
    });
  } catch {
    // fetch() itself threw - offline, DNS failure, CORS block, etc. Never
    // logs the error object (which could theoretically echo request details)
    // - only this generic, non-secret message propagates.
    throw new RuleEngineFetchError("network_error", "Could not reach the backend.");
  }

  if (res.status === 401) {
    throw new RuleEngineFetchError("unauthorized", "Authentication failed - check your API key.");
  }

  if (res.status === 422) {
    let detail = "Invalid symbol or timeframe.";
    try {
      const body = (await res.json()) as { error?: string };
      if (typeof body.error === "string" && body.error.length > 0) detail = body.error;
    } catch {
      // keep the generic default - the response body wasn't valid JSON
    }
    throw new RuleEngineFetchError("invalid", detail);
  }

  if (!res.ok) {
    throw new RuleEngineFetchError("network_error", `Unexpected response: HTTP ${res.status}`);
  }

  return (await res.json()) as RuleEngineLatestResponse;
}

// Sprint 16's approved viewer heuristic - explicitly NOT the backend's
// configured staleness value (atlas/monitoring.py's own threshold is a
// separate, unrelated setting for a different purpose - alerting, not
// display). stale_after = max(3 * timeframe duration, 5 minutes).
const TIMEFRAME_DURATION_MINUTES: Record<string, number> = {
  "1m": 1,
  "5m": 5,
  "15m": 15,
  "1h": 60,
};

export function isStale(occurredAtIso: string, timeframe: string): boolean {
  const durationMinutes = TIMEFRAME_DURATION_MINUTES[timeframe] ?? 5;
  const staleAfterMinutes = Math.max(3 * durationMinutes, 5);
  const occurredAt = new Date(occurredAtIso).getTime();
  if (Number.isNaN(occurredAt)) return false;
  const ageMinutes = (Date.now() - occurredAt) / 60_000;
  return ageMinutes > staleAfterMinutes;
}

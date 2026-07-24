// Sprint 11A Group 0A. Typed client for GET /status, reached through the
// same-origin BFF proxy (src/lib/proxyClient.ts) instead of lib/api.ts's
// legacy NEXT_PUBLIC_API_KEY pattern. Scoped to exactly the fields
// HeaderStatusDot and ConnectionStatusPanel actually read (database,
// tradingview, pickmytrade, claude) - research_snapshots/research_ledger
// are researchOpsApi.ts's own concern (fetchOpsStatus), not duplicated here.
//
// "status" is already on the proxy allowlist with no params (added in
// Sprint 10 Slice B for researchOpsApi.ts's own use) - no allowlist change
// needed for this migration.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export interface StatusResponse {
  database: { ok: boolean; detail: string };
  tradingview: { last_webhook_at: string | null; last_webhook_type: string | null };
  pickmytrade: {
    configured: boolean;
    last_forward_at: string | null;
    last_forward_ok: boolean | null;
    last_error: string | null;
  };
  claude: {
    configured: boolean;
    last_analysis_at: string | null;
    last_error: string | null;
  };
}

function isStatusResponse(value: unknown): value is StatusResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;

  if (typeof v.database !== "object" || v.database === null) return false;
  const database = v.database as Record<string, unknown>;
  if (typeof database.ok !== "boolean" || typeof database.detail !== "string") return false;

  if (typeof v.tradingview !== "object" || v.tradingview === null) return false;
  const tradingview = v.tradingview as Record<string, unknown>;
  if (
    !(tradingview.last_webhook_at === null || typeof tradingview.last_webhook_at === "string") ||
    !(tradingview.last_webhook_type === null || typeof tradingview.last_webhook_type === "string")
  ) {
    return false;
  }

  if (typeof v.pickmytrade !== "object" || v.pickmytrade === null) return false;
  const pickmytrade = v.pickmytrade as Record<string, unknown>;
  if (
    typeof pickmytrade.configured !== "boolean" ||
    !(pickmytrade.last_forward_at === null || typeof pickmytrade.last_forward_at === "string") ||
    !(pickmytrade.last_forward_ok === null || typeof pickmytrade.last_forward_ok === "boolean") ||
    !(pickmytrade.last_error === null || typeof pickmytrade.last_error === "string")
  ) {
    return false;
  }

  if (typeof v.claude !== "object" || v.claude === null) return false;
  const claude = v.claude as Record<string, unknown>;
  if (
    typeof claude.configured !== "boolean" ||
    !(claude.last_analysis_at === null || typeof claude.last_analysis_at === "string") ||
    !(claude.last_error === null || typeof claude.last_error === "string")
  ) {
    return false;
  }

  return true;
}

export function fetchStatus(): Promise<StatusResponse> {
  return proxyGet("status", {}, isStatusResponse);
}

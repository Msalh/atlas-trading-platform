// Sprint 10 Slice A. Lightweight, proxy-layer ACCESS logging - deliberately
// distinct from the permanent PromotionRecord audit trail, which already
// exists on the backend Ledger (atlas/research/stores.py's
// PromotionRecordTracker, readable via GET /api/v1/research/promotion) and
// needs nothing added here - see the Sprint 10 architecture review §4 for
// why conflating these two would recreate the same "audit" naming collision
// that review's §1 already flagged for the lineage endpoint.
//
// This logs only HTTP-request-shaped facts (method, path, status, timing)
// for operational visibility into the proxy itself - never a request or
// response body, never a header, never the API key. One line per request,
// written to the Next.js server process's own stdout - Railway's existing
// log capture for the frontend service, no new logging dependency.

export interface ProxyAccessLogEntry {
  method: string;
  path: string;
  status: number;
  durationMs: number;
}

export function logProxyAccess(entry: ProxyAccessLogEntry): void {
  console.log(`[proxy] ${entry.method} /api/proxy/${entry.path} -> ${entry.status} (${entry.durationMs.toFixed(0)}ms)`);
}

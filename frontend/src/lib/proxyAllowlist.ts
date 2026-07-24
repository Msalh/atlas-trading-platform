// UI v2, amendment 5; extended Sprint 10 Slice A for method-aware routing.
// The explicit, exact allowlist the BFF proxy route handler
// (app/api/proxy/[...path]/route.ts) checks every request against before
// doing anything else - implementation plan §5.2, Sprint 10 architecture
// review §4. Kept in its own module (not inline in route.ts) so it can be
// unit-tested directly without going through a live Next.js request/
// response cycle.
//
// Sprint 10: a path may now declare a GET config, a POST config, or both -
// the proxy checks BOTH the path AND the method before forwarding anything.
// This is still a closed, hand-authored table, never a wildcard or pattern
// match - the Sprint 10 review's own explicit line between a policy-aware
// BFF and a generic reverse proxy. A request whose method has no config for
// its path is rejected exactly like a path with no entry at all - the same
// generic 404, no indication of which methods WOULD have been allowed.
//
// GET config declares which query params get forwarded (filterAllowedParams).
// POST config declares which JSON body fields get forwarded
// (projectAllowedBody) - SHAPE projection only (which fields exist, at
// all), never business validation (e.g. "rationale must be non-blank",
// "decision must be one of three values") - that stays the backend's own
// job (atlas/research/models.py's PromotionRecord.__post_init__, the
// Pydantic request models), so there is exactly one place those rules can
// ever drift.
//
// Sprint 10 Slice B added `status` - the one operational health endpoint on
// this list (Dataset Health, above, is scoped to the frozen research
// baseline, never live system health).
// Every other unlisted path remains unreachable through this proxy.

export interface AllowedGetConfig {
  /** Query parameter names this path is allowed to forward - anything else on
   * the incoming request is silently dropped, never forwarded upstream. */
  params: readonly string[];
}

export interface AllowedPostConfig {
  /** JSON body field names this path is allowed to forward - anything else in
   * the incoming body is silently dropped, never forwarded upstream. Shape
   * projection only, never a business-rule check. */
  bodyFields: readonly string[];
}

export interface ProxyRouteConfig {
  GET?: AllowedGetConfig;
  POST?: AllowedPostConfig;
}

export type ProxyMethod = "GET" | "POST";

export const ALLOWED_PROXY_ROUTES: Readonly<Record<string, ProxyRouteConfig>> = {
  "rule-engine/latest": { GET: { params: ["symbol", "timeframe"] } },
  "setup-engine/latest": { GET: { params: ["symbol", "timeframe"] } },
  "setup-engine/episodes/live": { GET: { params: ["symbol", "timeframe", "window"] } },
  "research/re1/summary": { GET: { params: [] } },
  "research/re2/summary": { GET: { params: [] } },
  "research/dataset-health": { GET: { params: [] } },
  // Sprint 10 Slice A - the composed, read-only lineage walk (backend:
  // atlas/api/v1/research_lineage.py). No consuming page exists yet (that's
  // Slice D's own scope) - registered now so the endpoint this slice builds
  // is actually reachable through the one sanctioned security boundary the
  // Sprint 10 review requires, rather than existing backend-side with no
  // proxied path to it at all.
  "research/lineage": { GET: { params: ["promotion_id", "validation_id"] } },
  // Sprint 10 Slice B - Research Overview reads. Each declares only the
  // params this slice's page actually calls with (no snapshot_id/
  // promotion_id yet - those are Slice C/E's own scope, added when their
  // pages actually need them, the same discipline Slice A.1 already
  // established for research/promotion/decide).
  "status": { GET: { params: [] } },
  "research/leaderboard": { GET: { params: [] } },
  "research/promotion": { GET: { params: [] } },
  // Sprint 11A Group 0B - account risk snapshot (riskApi.ts). No params -
  // atlas/api/v1/risk.py always scopes to the single configured account.
  "risk": { GET: { params: [] } },
  // Sprint 11A Group 2 - Dashboard reads (tradesApi.ts, statsApi.ts).
  // "trades" forwards the same two query params atlas/api/v1/trades.py's
  // list_trades() itself accepts (limit, status) - nothing else.
  "trades/current": { GET: { params: [] } },
  "trades": { GET: { params: ["limit", "status"] } },
  "stats/today": { GET: { params: [] } },
  // Sprint 11A Group 4 - Analytics-page reads (analyticsApi.ts). No params -
  // atlas/api/v1/analytics.py always computes over the full trade history.
  "analytics/summary": { GET: { params: [] } },
  "analytics/equity-curve": { GET: { params: [] } },
  "analytics/breakdown": { GET: { params: [] } },
  // Sprint 11A Group 5 - Activity-page reads (activityApi.ts). Only "limit",
  // matching atlas/api/v1/activity.py's own single query param.
  "activity": { GET: { params: ["limit"] } },
  // Sprint 11A Group 7 - AI reads and the two explicitly enumerated
  // report-generation actions. The triggers accept no request body.
  "ai/notes": { GET: { params: ["trade_correlation_id", "note_type", "limit"] } },
  "ai/reports": { GET: { params: ["period", "limit"] } },
  "ai/reports/daily": { POST: { bodyFields: [] } },
  "ai/reports/weekly": { POST: { bodyFields: [] } },
  // Sprint 10 Slice E - Promotion Queue reads. read_promotion_candidates()
  // itself has existed since Sprint 9 (atlas/api/v1/promotion.py); this is
  // the first slice with a consuming page, exactly like research/lineage's
  // own Slice A -> Slice D gap. Read-only, no params (the endpoint always
  // scopes to the single latest snapshot server-side).
  "research/promotion/candidates": { GET: { params: [] } },
  // Sprint 10 Slice A.1 hardening: research/promotion/decide (POST) was
  // registered here during Slice A as an early proof of POST support, then
  // removed on review - it belongs to Slice E (the Promotion decision
  // form), and making a write action reachable through this security
  // boundary before its own consuming UI and architectural review exist is
  // scope leakage, not infrastructure. POST support itself (method-aware
  // allowlist, payload projection, the route handler) remains fully built
  // and tested - see proxyAllowlist.test.ts/route.test.ts, which exercise
  // it against a test-only fixture path rather than a real production
  // entry. Slice E adds its own real entry when the decision form and its
  // review actually happen.
};

export function isAllowedProxyPath(path: string): path is keyof typeof ALLOWED_PROXY_ROUTES {
  return Object.prototype.hasOwnProperty.call(ALLOWED_PROXY_ROUTES, path);
}

export function isBodylessProxyPost(path: string): boolean {
  const post = ALLOWED_PROXY_ROUTES[path]?.POST;
  return post != null && post.bodyFields.length === 0;
}

// Sprint 10 Slice A.1: every lookup function below takes an optional `routes`
// table, defaulting to the real ALLOWED_PROXY_ROUTES - a testability
// parameter only, never a production capability. route.ts always calls these
// with the default (the real table always governs actual request handling);
// tests use it to exercise POST/projection behavior against a local fixture
// path without needing a real write endpoint registered in production
// config (see §1's own reasoning above for why one shouldn't be, ahead of
// its own slice).

export function isAllowedProxyMethod(
  path: string,
  method: ProxyMethod,
  routes: Readonly<Record<string, ProxyRouteConfig>> = ALLOWED_PROXY_ROUTES,
): boolean {
  const config = routes[path];
  return config != null && config[method] != null;
}

/** Builds a fresh URLSearchParams containing only the params declared for
 * this path's GET config, in their original values - never a blanket
 * passthrough of whatever the browser sent. Empty (never throws) for a path
 * with no GET config at all. */
export function filterAllowedParams(
  path: string,
  incoming: URLSearchParams,
  routes: Readonly<Record<string, ProxyRouteConfig>> = ALLOWED_PROXY_ROUTES,
): URLSearchParams {
  const allowed = routes[path]?.GET;
  const filtered = new URLSearchParams();
  if (!allowed) return filtered;
  for (const name of allowed.params) {
    const value = incoming.get(name);
    if (value !== null) filtered.set(name, value);
  }
  return filtered;
}

/** Builds a fresh plain object containing only the fields declared for this
 * path's POST config, taken from the incoming (already-parsed-as-JSON-
 * object) body - never a blanket passthrough. Empty (never throws) for a
 * path with no POST config at all. Field VALUES are forwarded as-is,
 * whatever type the browser sent - this is shape/field-name projection,
 * never a type or business-rule check (see this module's own header
 * comment for why that stays the backend's job). */
export function projectAllowedBody(
  path: string,
  incoming: Record<string, unknown>,
  routes: Readonly<Record<string, ProxyRouteConfig>> = ALLOWED_PROXY_ROUTES,
): Record<string, unknown> {
  const allowed = routes[path]?.POST;
  const projected: Record<string, unknown> = {};
  if (!allowed) return projected;
  for (const field of allowed.bodyFields) {
    if (Object.prototype.hasOwnProperty.call(incoming, field)) {
      projected[field] = incoming[field];
    }
  }
  return projected;
}

// Sprint 11A Group 6 - the one dynamic-ID path this proxy supports:
// GET /trades/{tradeId} (tradesApi.ts's fetchTradeDetail). This is
// deliberately NOT a second entry in ALLOWED_PROXY_ROUTES, and NOT a
// wildcard/prefix rule like "trades/**" - the table above stays a closed,
// exact-string map exactly as documented at the top of this file. This is
// a separate, single-purpose structural parser for exactly one shape:
// GET only, exactly two path segments, the first literally "trades", the
// second a non-empty trade ID with no embedded "/" - functionally
// equivalent to the backend's own typed path parameter
// (`@router.get("/trades/{correlation_id}")`, atlas/api/v1/trades.py),
// just re-declared here so the proxy can validate it before forwarding
// anything. route.ts only consults this after the static table above has
// already been checked and found no match, so a real static entry (e.g.
// "trades" or "trades/current") is always resolved by the table first and
// never reaches this parser.
//
// Deliberately operates on the raw pathSegments ARRAY Next.js already
// split for us (route.ts's `params.path`), not a rejoined/resplit string -
// this sidesteps any ambiguity about what a decoded "%2F" inside one raw
// URL segment would look like after a join+split round trip. If Next.js
// ever decodes an inbound "%2F" into a literal "/" character embedded
// within a single array element (a known routing edge case across many
// frameworks), that element still fails the exact-two-segments shape as
// far as THIS function's caller is concerned once re-examined - and the
// `id.includes("/")` check below rejects it explicitly and directly,
// rather than relying on that implicit collapse.
const TRADE_DETAIL_ID_MAX_LENGTH = 256; // generous - real correlation_ids are well under 40 chars

export function parseTradeDetailPath(pathSegments: readonly string[]): string | null {
  if (pathSegments.length !== 2) return null;
  const [first, id] = pathSegments;
  if (first !== "trades") return null;
  if (id.length === 0 || id.length > TRADE_DETAIL_ID_MAX_LENGTH) return null;
  if (id.includes("/")) return null;
  return id;
}

const AI_INTELLIGENCE_ID_MAX_LENGTH = 256;

/** The only dynamic AI route: exactly GET ai/intelligence/{correlationId}.
 * This parser is intentionally separate from trade detail and from the
 * static table; it is not a prefix rule or a generic AI wildcard. */
export function parseAiIntelligencePath(pathSegments: readonly string[]): string | null {
  if (
    pathSegments.length !== 3 ||
    pathSegments[0] !== "ai" ||
    pathSegments[1] !== "intelligence"
  ) return null;
  const id = pathSegments[2];
  if (id.length === 0 || id.length > AI_INTELLIGENCE_ID_MAX_LENGTH) return null;
  if (id.includes("/")) return null;
  return id;
}

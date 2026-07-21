// UI v2, amendment 5. The explicit, exact allowlist the BFF proxy route
// handler (app/api/proxy/[...path]/route.ts) checks every request against
// before doing anything else - implementation plan §5.2. Kept in its own
// module (not inline in route.ts) so it can be unit-tested directly
// without going through a live Next.js request/response cycle.
//
// No operational health endpoint (/health, /status) is included - no UI v2
// page currently calls one (Dataset Health is scoped to the frozen
// research baseline, never live system health). A future page needing one
// would add it here explicitly, by name - this proxy never forwards an
// unlisted path.

export interface AllowedProxyRoute {
  /** Query parameter names this path is allowed to forward - anything else on
   * the incoming request is silently dropped, never forwarded upstream. */
  params: readonly string[];
}

export const ALLOWED_PROXY_PATHS: Readonly<Record<string, AllowedProxyRoute>> = {
  "rule-engine/latest": { params: ["symbol", "timeframe"] },
  "setup-engine/latest": { params: ["symbol", "timeframe"] },
  "setup-engine/episodes/live": { params: ["symbol", "timeframe", "window"] },
  "research/re1/summary": { params: [] },
  "research/re2/summary": { params: [] },
  "research/dataset-health": { params: [] },
};

export function isAllowedProxyPath(path: string): path is keyof typeof ALLOWED_PROXY_PATHS {
  return Object.prototype.hasOwnProperty.call(ALLOWED_PROXY_PATHS, path);
}

/** Builds a fresh URLSearchParams containing only the params declared for
 * this path, in their original values - never a blanket passthrough of
 * whatever the browser sent. */
export function filterAllowedParams(path: string, incoming: URLSearchParams): URLSearchParams {
  const allowed = ALLOWED_PROXY_PATHS[path];
  const filtered = new URLSearchParams();
  if (!allowed) return filtered;
  for (const name of allowed.params) {
    const value = incoming.get(name);
    if (value !== null) filtered.set(name, value);
  }
  return filtered;
}

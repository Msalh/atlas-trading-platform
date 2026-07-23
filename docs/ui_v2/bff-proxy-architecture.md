# BFF Proxy Architecture (Sprint 10 Slice A, hardened in Slice A.1)

**Status**: implemented and tested (backend + frontend), not yet consumed by any page. This document describes the security boundary itself - `src/app/api/proxy/[...path]/route.ts` and `src/lib/proxyAllowlist.ts` - extended in Sprint 10 Slice A to support `POST` alongside the existing `GET`, then hardened in Slice A.1 after an adversarial self-review surfaced real scope leakage and a performance issue (both corrected, both covered below). It assumes the Sprint 10 architecture review's own conclusion (§4): this proxy is a **policy-aware Backend-for-Frontend**, never a generic reverse proxy. Every rule below exists to keep that distinction real, not aspirational.

---

## 1. Why this exists

The Atlas backend (`atlas.main:app`) requires a shared `API_KEY` on every authenticated route. That key must never reach the browser - if it did, anyone who opened DevTools could extract it and call the backend directly, bypassing every rate limit and audit surface the backend has. UI v2's existing pages (Research Overview, Dataset Health, Market View, etc.) already solve this for reads: the browser calls this app's own `/api/proxy/*` route (same-origin, no key needed), and only the Next.js **server** attaches the real key before forwarding to the backend. Sprint 10 needs the same guarantee for **writes** (a promotion decision, a research run) - this document is that extension.

## 2. Request flow

```
Browser
  |
  |  fetch("/api/proxy/<path>", { method: "GET" | "POST", body?: {...} })
  |  (same-origin - no Authorization header, no API key, ever)
  v
Next.js BFF  (src/app/api/proxy/[...path]/route.ts)
  |
  |  1. Method-aware allowlist check  (src/lib/proxyAllowlist.ts)
  |     isAllowedProxyMethod(path, "GET" | "POST")
  |     -> unknown path, OR known path with no config for this method: 404, fetch() never called
  |
  |  2. Payload/param projection  (same module)
  |     GET:  filterAllowedParams()  - keep only declared query params
  |     POST: projectAllowedBody()   - keep only declared JSON body FIELD NAMES
  |     (shape/name projection only - see §4. Never a business-rule check.)
  |
  |  3. Header construction
  |     - Accept: application/json always
  |     - Authorization: Bearer <ATLAS_API_KEY> - the server's own env var,
  |       NEVER anything from the incoming request
  |     - Content-Type: application/json, POST only
  |     - every other browser-supplied header is dropped
  |
  |  4. Access logging  (src/lib/proxyAccessLog.ts) - see §6
  |
  v
Atlas Backend  (atlas.main:app, /api/v1/<path>)
  |
  |  - re-validates everything (Pydantic request models, PromotionRecord.__post_init__, etc.)
  |  - this is the ONLY place business rules are enforced - see §3
  v
Response (JSON body + status code)
  |
  v
Next.js BFF
  |
  |  - non-JSON upstream body -> sanitized 502, never the raw body
  |  - network/timeout failure -> sanitized 502, never the raw exception
  |  - otherwise: the backend's own body + status, passed through verbatim
  |    (already safe by construction - the backend's own error responses
  |    never contain the API key, an Authorization header, or a stack trace)
  |
  v
Browser
```

**Where each concern lives, restated as a table** (this is the review's §4 answer, now as implemented):

| Concern | Lives in the proxy? | Lives in the backend? |
|---|---|---|
| Route allowlist (which paths/methods are reachable at all) | **Yes** - the one thing this layer is *for* | No opinion - the backend has no concept of "the proxy" |
| Payload/param **shape** projection (which field names are forwarded) | **Yes** | No - irrelevant once a request reaches the backend |
| Business/domain validation (non-blank rationale, valid decision enum, etc.) | **No** | **Yes** - Pydantic models, `PromotionRecord.__post_init__` |
| The permanent audit trail (who decided what, when) | **No** | **Yes** - `PromotionRecordTracker`, already existed before this slice |
| HTTP-level access logging (method/path/status/timing) | **Yes** - see §6 | No - the backend has its own separate request logging, unrelated |
| Authorization (is this API key valid at all) | No - the proxy has no key of its own to check against | **Yes** - `require_api_key`, enforced against every caller, not only proxied ones |
| Rate limiting | No | **Yes** - `atlas/rate_limit.py`, unchanged |
| Orchestration (composing multiple backend calls into one response) | **Never** - see §3 | Where it belongs, when needed (e.g. `GET /research/lineage` composes its own walk server-side) |
| Caching, persistence | **Never**, anywhere in this layer | N/A |

## 3. What the proxy explicitly does NOT do

This is the boundary the Sprint 10 review drew, and it's the one thing to protect against scope creep in every future slice that touches this file:

- **No wildcard or pattern-based routing.** `ALLOWED_PROXY_ROUTES` is a closed, hand-authored, committed object literal. A new capability always means a new named entry, never a regex or prefix match.
- **No business validation.** `projectAllowedBody()` only checks whether a field is *declared* for a path - it never inspects a field's *value* (type, blankness, enum membership). A malformed value is forwarded to the backend exactly as sent, and the backend's own 422 comes back verbatim. Duplicating a validation rule in both places is exactly how the two drift out of sync later - so it only ever lives once, in the backend.
- **No orchestration.** `forwardToUpstream()` makes exactly one upstream call per incoming request, always. A capability that needs data from several backend entities (e.g. the full Promotion → Snapshot → Validation → Evidence → Experiment → Realization walk) is built as **one backend endpoint** (`GET /research/lineage`) that does its own composition server-side - never assembled from several proxy-side calls stitched together. The moment this file starts composing responses, it has stopped being a BFF and started being the kind of orchestrating reverse proxy the review rejected.
- **No caching.** Every GET is issued with `cache: "no-store"`.
- **No persistence of any kind.** This layer holds no state between requests beyond the one key read from `process.env` per call.

## 4. Allowlist structure

`src/lib/proxyAllowlist.ts` exports:

```ts
export interface AllowedGetConfig {
  params: readonly string[];       // query param names this path forwards
}

export interface AllowedPostConfig {
  bodyFields: readonly string[];   // JSON body field names this path forwards
}

export interface ProxyRouteConfig {
  GET?: AllowedGetConfig;
  POST?: AllowedPostConfig;
}

export const ALLOWED_PROXY_ROUTES: Readonly<Record<string, ProxyRouteConfig>>;
```

A path may declare `GET`, `POST`, or both. A request is only ever forwarded when **both** the path and the method have a matching entry - `isAllowedProxyMethod(path, method)` is the one function the route handler asks. There is deliberately no way to declare "any method" or "any path" - every reachable path+method pair must be named.

As of Slice A.1:

| Path | GET | POST |
|---|---|---|
| `rule-engine/latest` | `symbol`, `timeframe` | - |
| `setup-engine/latest` | `symbol`, `timeframe` | - |
| `setup-engine/episodes/live` | `symbol`, `timeframe`, `window` | - |
| `research/re1/summary` | *(none)* | - |
| `research/re2/summary` | *(none)* | - |
| `research/dataset-health` | *(none)* | - |
| `research/lineage` | `promotion_id`, `validation_id` | - |

`research/lineage` is new in Slice A. It has no consuming page yet (that's Slice D's own scope) - it's registered now because the backend capability it fronts is this slice's own deliverable, and per the review's own §4, a backend action isn't safely reachable from the browser until it has an allowlist entry. Registering the entry is BFF configuration, not UI work - no form, page, or component was built to justify it.

**No path declares a `POST` config as of Slice A.1, and that is intentional.** Slice A originally also registered `research/promotion/decide` (POST) as an early proof that the POST mechanism worked end-to-end. On the adversarial review before certification, that entry was identified as real scope leakage and removed:

- `research/promotion/decide` is Slice E's own deliverable - the Promotion decision form and its own architectural review haven't happened yet. Making the write action reachable through this security boundary ahead of that review is exactly the kind of thing "independently reviewable, independently testable, independently committable" slices exist to prevent - Slice A's diff should be reviewable purely on "does the BFF and the lineage endpoint work," not "and here's an early preview of Slice E's write path too."
- It was also, structurally, dead attack surface: nothing in the shipped frontend called it, so it existed as a real, reachable write endpoint with no feature depending on it yet.

**The POST mechanism itself is not weakened by this removal** - `isAllowedProxyMethod`, `projectAllowedBody`, and the route handler's `POST` export are unchanged and fully covered by tests (`proxyAllowlist.test.ts`, `route.test.ts`), exercised against a local, clearly-named test-only fixture path (`test-fixture/post-only`) rather than a real production entry. Both `isAllowedProxyMethod` and `projectAllowedBody` (and `filterAllowedParams`) take an optional `routes` table parameter, defaulting to the real `ALLOWED_PROXY_ROUTES`, specifically so tests can inject a fixture without needing anything registered in production config - the route handler itself always calls these with the default, so real request handling is governed exclusively by the real table. Slice E adds its own real `research/promotion/decide` entry when the decision form and its own review actually happen - at that point this table gains exactly one more line, nothing about the mechanism changes.

## 5. POST policy and payload projection rules

For a path with a `POST` config:

1. The incoming request body must parse as valid JSON **and** be a plain object (not an array, not a primitive, not `null`) - anything else is rejected with `400` before any upstream call is attempted.
2. `projectAllowedBody(path, body)` builds a **new** object containing only the keys listed in that path's `bodyFields`, taken from the incoming body **only if present** - a field the browser omitted is simply absent from the projected body, never defaulted or invented.
3. A field's **value** is forwarded exactly as received, with no type coercion or check - `projectAllowedBody` answers "is this field name declared for this path," nothing about what the value should be. The backend's own Pydantic model is the only place a wrong type or an invalid enum value is ever rejected.
4. Any field not in `bodyFields` - however it got there, including a client deliberately trying to inject one (e.g. a spoofed `realization_id`) - is silently dropped and never reaches the backend.
5. The projected body, and only the projected body, is what gets sent upstream, as `Content-Type: application/json`.

## 6. Access logging behavior

`src/lib/proxyAccessLog.ts`'s `logProxyAccess()` is called exactly once per request, by both the `GET` and `POST` handlers, after a response has been produced (success, rejection, or sanitized failure - every path through the handler logs). One line to the Next.js server process's own `stdout` (Railway's existing log capture for the frontend service - no new logging dependency, no new destination):

```
[proxy] POST /api/proxy/research/promotion/decide -> 200 (43ms)
```

**What is logged**: HTTP method, the proxied path, the response status code, elapsed time in milliseconds.

**What is never logged**: the request body, the response body, any header (including `Authorization`/the API key), the client's IP, or any value from either. This is deliberately narrower than "audit logging" in the compliance sense - the review's own §4 distinguishes the two explicitly. The *permanent* record of a promotion decision is `PromotionRecordTracker` on the backend, unaffected by and unrelated to this log line; this line exists only so an operator can see request-level traffic/timing through the proxy itself, the same category of thing as a web server's own access log, nothing more.

## 7. Unhandled methods - verified empirically, not assumed

This route file exports exactly `GET` and `POST`. Every other HTTP method's behavior is entirely Next.js App Router's own framework behavior for a route file with that export set - none of it is code this file implements. Rather than document that from memory, it was checked directly: `npm run dev` (a real, running `next dev` server, no backend required for most of these), then `curl -X <method>` against a real allowed path (`research/dataset-health`) and a disallowed one (`trades`). Observed, exact results:

| Method | Status | Notes |
|---|---|---|
| `PUT` | `405 Method Not Allowed` | No `Allow` header on the response. |
| `PATCH` | `405 Method Not Allowed` | Same. |
| `DELETE` | `405 Method Not Allowed` | Same. |
| `HEAD` | Mirrors whatever `GET` would return, body stripped | Verified against a disallowed path: `404`, `Content-Length: 0` - i.e. Next.js runs the real `GET` handler (including the allowlist rejection) and drops the body per HTTP semantics, it does not short-circuit to a blanket `200`. |
| `OPTIONS` | `204 No Content` | `Allow: GET, HEAD, OPTIONS, POST` - generated from exactly the methods this file exports (`GET`, `POST`) plus the two Next.js always adds. Same for every path, allowed or not - this is a route-file-level response, not a per-path one. |

The one thing actually within this file's control - and the one thing a Vitest unit test (which calls the exported functions directly, never through a real server) can meaningfully assert - is that no accidental handler for any of these methods exists: `Object.keys(routeModule)` must equal exactly `["GET", "POST"]`. That's what `route.test.ts`'s "unhandled methods" test checks. If a future slice legitimately needs `PUT`/`DELETE` (there is no such need today), it must be added as an explicit, reviewed export, exactly like `POST` was added in Slice A - never left to happen by accident.

## 8. Lineage endpoint: one read per store

`atlas/api/v1/research_lineage.py`'s Slice A implementation called `.get(id)` once per referenced id while walking the chain (once per `evidence_id`, once per `experiment_id`, and so on). Since every Ledger store's `.get()`/`.all()` independently re-reads and re-parses its entire JSONL file from scratch (`atlas/research/stores.py` has no caching or indexing by design at this scale), a single lineage request could issue **8-9 full file scans** - by a wide margin the heaviest read pattern of any endpoint in the Research Engine, found during the adversarial review before certification.

**Slice A.1 correction**: `_read_lineage_maps()` reads all six touched stores (`promotions`, `leaderboard_snapshots`, `validation_results`, `evidence`, `experiments`, `realizations`) via `.all()` **exactly once**, up front, building an id-keyed `dict` for each. Every subsequent "lookup" in the walk (`_matching_entries()`, `_walk_from_validation_ids()`, the final promotion-history filter) is a plain in-memory dict access against those maps - never a second call into a store. This is a mechanically-proven property, not an inspection-only claim: `test_research_lineage_api.py::test_lineage_reads_each_ledger_store_at_most_once_per_request` wraps every touched store's `.all()`/`.get()` with a call counter and asserts `.all()` is called exactly once per store and `.get()` is never called at all - a test that would fail against the original Slice A implementation.

**External behavior is unchanged** - same endpoint, same query parameters, same response shape (every field, every key), same status codes, same warning text for every degraded/missing-reference case. This was verified by the full pre-existing lineage test suite (all 9 Slice A tests) passing unmodified against the refactored implementation, plus the one new test above. This section exists specifically so a future reader doesn't have to re-derive from the diff that this was a pure internal optimization.

## 9. What changed vs. Slice A's own scope, precisely

**Slice A:**
- `src/lib/proxyAllowlist.ts` - rewritten: `ALLOWED_PROXY_PATHS: Record<string, { params }>` became `ALLOWED_PROXY_ROUTES: Record<string, { GET?, POST? }>`. `isAllowedProxyPath` kept (still answers "does this path exist at all"); `isAllowedProxyMethod` added; `filterAllowedParams` unchanged in behavior for every pre-existing GET path; `projectAllowedBody` added.
- `src/app/api/proxy/[...path]/route.ts` - `GET` handler's behavior is unchanged for every pre-existing path (same allowlist check semantics, same header/timeout/error handling); a new `POST` handler was added, sharing the same upstream-forwarding logic via a small internal helper; access logging added to both.
- `src/lib/proxyAccessLog.ts` - new, small, single-purpose.
- `src/lib/proxyClient.ts` - `proxyGet<T>` unchanged in behavior; `proxyPost<T>` added alongside it, sharing response-parsing/error-mapping logic with `proxyGet` via a private helper.
- Backend: `atlas/api/v1/research_lineage.py` (new), `atlas/main.py` (router registration), `tests/test_research_whole_pipeline_dependency_audit.py` (new sanctioned consumer entry).

**Slice A.1 (hardening, after the adversarial review below this document's own git history):**
- `src/lib/proxyAllowlist.ts` - `research/promotion/decide` (POST) entry removed (§4); `isAllowedProxyMethod`/`filterAllowedParams`/`projectAllowedBody` each gained an optional `routes` parameter, defaulting to the real table, purely for test injection - production behavior (the default) is unchanged.
- `src/app/api/proxy/[...path]/__tests__/route.test.ts`, `src/lib/__tests__/proxyAllowlist.test.ts` - POST/projection tests repointed from the removed production path to a local test-only fixture path (`test-fixture/post-only`); explicit regression tests added proving `research/promotion/decide` is now unreachable via either method; a new "unhandled methods" test added (§7).
- `atlas/api/v1/research_lineage.py` - internal-only refactor to read each Ledger store once per request (§8); API/response shape/status codes/behavior unchanged.
- `docs/ui_v2/bff-proxy-architecture.md` (this document) - §4 rewritten, §7 and §8 added.

**Request flow (§2) is structurally unchanged by Slice A.1** - same four-step proxy-side pipeline, same header/error/logging behavior. Only the allowlist's *contents* and the lineage endpoint's *internal* read pattern changed; the mechanism both diagrams describe is identical to Slice A's.

No page, route, form, or component was added in either slice.

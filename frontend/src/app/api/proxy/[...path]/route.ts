// UI v2, amendment 3/5; extended Sprint 10 Slice A for POST. The one
// Backend-for-Frontend proxy route handler every UI v2 page's data fetch
// (and, from Sprint 10 onward, every write action) goes through - browser
// -> this route (same-origin, no key needed) -> Atlas API with a
// server-only ATLAS_API_KEY attached. This file never runs in the browser
// bundle (Next.js Route Handlers are server-only), so ATLAS_API_KEY is
// never shipped to the client - unlike the rest of this app's existing
// pages, which still use NEXT_PUBLIC_API_KEY directly from the browser (a
// disclosed, deliberately-deferred inconsistency - implementation plan
// §5.3/§5.4, not fixed here).
//
// GET and POST only, an explicit method-aware path allowlist
// (src/lib/proxyAllowlist.ts) checked before anything else runs, declared-
// field-only forwarding (query params for GET, JSON body fields for POST -
// never a blind passthrough of either), no browser-supplied headers
// forwarded (the server's own ATLAS_API_KEY always wins), a bounded
// upstream timeout, and error bodies that never contain a secret, an
// Authorization header, or a raw stack trace - see docs/ui_v2/market-
// intelligence-dashboard-implementation-plan.md §5.2 and the Sprint 10
// architecture review §4.
//
// Sprint 10 architecture review §4's own explicit boundary, restated here
// because it is the one thing this file must never grow into: no
// orchestration (never composes more than one upstream call - a walk like
// GET /research/lineage is a single backend endpoint, precisely so this
// proxy never has to fan out and stitch responses together), no business
// validation (a projected field's VALUE is forwarded as-is; only whether
// the field is *declared at all* is checked here - "rationale must be
// non-blank" stays the backend's job), no caching, no persistence of any
// kind, and no wildcard/pattern routing - every reachable path+method pair
// is named explicitly in the allowlist.

import { NextRequest, NextResponse } from "next/server";
import {
  filterAllowedParams,
  isAllowedProxyMethod,
  projectAllowedBody,
} from "@/lib/proxyAllowlist";
import { logProxyAccess } from "@/lib/proxyAccessLog";

const UPSTREAM_TIMEOUT_MS = 10_000;

function atlasApiBaseUrl(): string {
  // Read fresh per request, not cached at module-import time - both more
  // correct (never assumes an env var is fixed for the process lifetime)
  // and directly testable without module-reset gymnastics.
  return process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
}

function atlasApiKey(): string | undefined {
  // Server-only - deliberately NOT NEXT_PUBLIC_-prefixed, so it is never
  // bundled into any client-shipped JavaScript.
  return process.env.ATLAS_API_KEY;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The one place either handler below actually talks to the backend - a
 * single fetch, never more than one per incoming request (see this file's
 * own header comment on why orchestration never belongs here). */
async function forwardToUpstream(
  method: "GET" | "POST",
  upstreamUrl: string,
  body: Record<string, unknown> | undefined,
): Promise<NextResponse> {
  // Only Accept (and, for POST, Content-Type) are ever set here - never any
  // browser-supplied header, and never Authorization from the incoming
  // request (the server's own key always replaces it).
  const headers: HeadersInit = { Accept: "application/json" };
  const key = atlasApiKey();
  if (key) headers.Authorization = `Bearer ${key}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      cache: "no-store",
    });
  } catch {
    // A network error, DNS failure, or timeout - never surface the raw
    // exception (it can contain hostnames/stack traces), only a generic,
    // sanitized message.
    return NextResponse.json({ ok: false, error: "upstream request failed" }, { status: 502 });
  }

  // The backend's own response bodies (both success and its structured
  // {ok: false, error: "..."} validation errors) never contain the shared
  // API key, an Authorization header, or a stack trace by construction -
  // safe to pass through verbatim, status code included.
  let responseBody: unknown;
  try {
    responseBody = await upstreamResponse.json();
  } catch {
    return NextResponse.json({ ok: false, error: "upstream returned a non-JSON response" }, { status: 502 });
  }

  return NextResponse.json(responseBody, { status: upstreamResponse.status });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const startedAt = Date.now();
  const { path: pathSegments } = await params;
  const path = pathSegments.join("/");

  let response: NextResponse;
  if (!isAllowedProxyMethod(path, "GET")) {
    // No indication of what WOULD have been allowed (including whether this
    // path exists at all for a different method) - avoid enumeration.
    response = NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  } else {
    const filteredParams = filterAllowedParams(path, request.nextUrl.searchParams);
    const query = filteredParams.toString();
    const upstreamUrl = `${atlasApiBaseUrl()}/api/v1/${path}${query ? `?${query}` : ""}`;
    response = await forwardToUpstream("GET", upstreamUrl, undefined);
  }

  logProxyAccess({ method: "GET", path, status: response.status, durationMs: Date.now() - startedAt });
  return response;
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const startedAt = Date.now();
  const { path: pathSegments } = await params;
  const path = pathSegments.join("/");

  let response: NextResponse;
  if (!isAllowedProxyMethod(path, "POST")) {
    response = NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  } else {
    let parsedBody: unknown;
    try {
      parsedBody = await request.json();
    } catch {
      parsedBody = undefined;
    }

    if (!isPlainObject(parsedBody)) {
      // A client-side shape problem (malformed/absent JSON body) - distinct
      // from 502 (an upstream problem), and never forwarded upstream at all.
      response = NextResponse.json({ ok: false, error: "request body must be a JSON object" }, { status: 400 });
    } else {
      const projected = projectAllowedBody(path, parsedBody);
      const upstreamUrl = `${atlasApiBaseUrl()}/api/v1/${path}`;
      response = await forwardToUpstream("POST", upstreamUrl, projected);
    }
  }

  logProxyAccess({ method: "POST", path, status: response.status, durationMs: Date.now() - startedAt });
  return response;
}

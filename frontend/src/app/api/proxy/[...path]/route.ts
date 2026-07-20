// UI v2, amendment 3/5. The one Backend-for-Frontend proxy route handler
// every UI v2 page's data fetch goes through - browser -> this route
// (same-origin, no key needed) -> Atlas API with a server-only
// ATLAS_API_KEY attached. This file never runs in the browser bundle
// (Next.js Route Handlers are server-only), so ATLAS_API_KEY is never
// shipped to the client - unlike the rest of this app's existing pages,
// which still use NEXT_PUBLIC_API_KEY directly from the browser (a
// disclosed, deliberately-deferred inconsistency - implementation plan
// §5.3/§5.4, not fixed here).
//
// GET only, an explicit path allowlist (src/lib/proxyAllowlist.ts) checked
// before anything else runs, declared-query-param-only forwarding, no
// browser-supplied headers forwarded (the server's own ATLAS_API_KEY always
// wins), a bounded upstream timeout, and error bodies that never contain a
// secret, an Authorization header, or a raw stack trace - see
// docs/ui_v2/market-intelligence-dashboard-implementation-plan.md §5.2.

import { NextRequest, NextResponse } from "next/server";
import { filterAllowedParams, isAllowedProxyPath } from "@/lib/proxyAllowlist";

const UPSTREAM_TIMEOUT_MS = 10_000;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  // Read fresh per request, not cached at module-import time - both more
  // correct (never assumes an env var is fixed for the process lifetime)
  // and directly testable without module-reset gymnastics.
  const atlasApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  // Server-only - deliberately NOT NEXT_PUBLIC_-prefixed, so it is never
  // bundled into any client-shipped JavaScript.
  const atlasApiKey = process.env.ATLAS_API_KEY;

  const { path: pathSegments } = await params;
  const path = pathSegments.join("/");

  if (!isAllowedProxyPath(path)) {
    // No indication of what WOULD have been allowed - avoid enumeration.
    return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  }

  const filteredParams = filterAllowedParams(path, request.nextUrl.searchParams);
  const query = filteredParams.toString();
  const upstreamUrl = `${atlasApiBaseUrl}/api/v1/${path}${query ? `?${query}` : ""}`;

  // Only Accept is forwarded from the browser's own request headers -
  // never Authorization (the server's own key always replaces it) and
  // never any other browser-supplied header.
  const headers: HeadersInit = { Accept: "application/json" };
  if (atlasApiKey) headers.Authorization = `Bearer ${atlasApiKey}`;

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl, {
      headers,
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
  // API key, an Authorization header, or a stack trace by construction
  // (atlas/api/v1/research.py and setup_engine.py's own error handling) -
  // safe to pass through verbatim, status code included.
  let body: unknown;
  try {
    body = await upstreamResponse.json();
  } catch {
    return NextResponse.json({ ok: false, error: "upstream returned a non-JSON response" }, { status: 502 });
  }

  return NextResponse.json(body, { status: upstreamResponse.status });
}

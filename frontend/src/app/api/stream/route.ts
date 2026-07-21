// Production hardening. Same-origin SSE proxy for GET /api/v1/stream - browsers'
// native EventSource cannot set custom request headers, so it previously had to
// carry the shared API key as a `?api_key=...` query parameter directly to the
// backend. That value showed up verbatim in Railway's own access logs, reverse-proxy
// logs, browser history, and any request-level monitoring - a real, observed leak,
// not a hypothetical one (see docs/ui_v2/production-hardening-plan.md).
//
// This route closes that: browser -> this route (same-origin, no key anywhere in the
// URL) -> Atlas API's /api/v1/stream with a server-only ATLAS_API_KEY attached as a
// normal Authorization header, exactly the same trust boundary the JSON BFF proxy
// (app/api/proxy/[...path]/route.ts) already established - this route never runs in
// the browser bundle, so ATLAS_API_KEY is never shipped to the client.
//
// Unlike the JSON proxy, this is a genuine pass-through stream, not a
// buffer-then-re-serialize: the upstream response body is piped to the client as-is,
// with no artificial timeout (a healthy SSE connection is meant to stay open
// indefinitely - the keepalive comment lines atlas/api/v1/stream.py already sends
// are what keep any intermediate proxy from timing it out). The incoming request's
// own AbortSignal is forwarded to the upstream fetch, so closing the browser's
// EventSource (or a frontend-side connection drop) also stops pulling from upstream,
// rather than leaking an orphaned server-to-server connection.
//
// If the upstream backend is unreachable, EventSource treats any non-2xx response as
// a connection failure regardless of body content-type - it fires its own onerror
// handler and retries automatically per the SSE spec, exactly the same
// "connecting -> closed -> reconnect" cycle frontend/src/lib/live-updates.tsx already
// handles for a plain network blip. No new failure mode is introduced.

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  // Read fresh per request, not cached at module-import time - same discipline as
  // app/api/proxy/[...path]/route.ts.
  const atlasApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  // Server-only - deliberately NOT NEXT_PUBLIC_-prefixed, so it is never bundled into
  // any client-shipped JavaScript.
  const atlasApiKey = process.env.ATLAS_API_KEY;

  const headers: HeadersInit = { Accept: "text/event-stream" };
  if (atlasApiKey) headers.Authorization = `Bearer ${atlasApiKey}`;

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(`${atlasApiBaseUrl}/api/v1/stream`, {
      headers,
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    // A network error, DNS failure, or client-initiated abort - never surface the
    // raw exception (it can contain hostnames/stack traces), only a generic,
    // sanitized message. EventSource treats this exactly like any other failed
    // connection attempt and retries on its own.
    return Response.json({ ok: false, error: "upstream request failed" }, { status: 502 });
  }

  if (!upstreamResponse.body) {
    return Response.json({ ok: false, error: "upstream returned no stream body" }, { status: 502 });
  }

  // A genuine pass-through - the upstream body is never read/buffered/re-serialized
  // here, only piped straight to the client, preserving the upstream status code
  // (e.g. a 401 if ATLAS_API_KEY is ever misconfigured - already a sanitized,
  // secret-free body by construction, see atlas/api/security.py).
  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

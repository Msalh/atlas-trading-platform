import { NextResponse } from "next/server";

const TIMEOUT_MS = 5_000;
const PATHS = {
  health: "/health",
  readiness: "/readiness",
  latest:
    "/api/v1/trader-now?symbol=MNQ&timeframe=5m&strategy_id=displacement_volume_context",
  operations: "/api/v1/operations/status",
} as const;

export type UpstreamSource = keyof typeof PATHS;

export async function readUpstream(source: UpstreamSource): Promise<NextResponse> {
  const baseUrl = process.env.TRADER_NOW_INTERNAL_URL?.replace(/\/$/, "");
  const apiKey = process.env.TRADER_NOW_API_KEY;
  if (!baseUrl || !apiKey) {
    return NextResponse.json(
      { ok: false, code: "dashboard_configuration_unavailable" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  const headers: HeadersInit = { Accept: "application/json" };
  if (source !== "health") headers.Authorization = `Bearer ${apiKey}`;
  try {
    const response = await fetch(`${baseUrl}${PATHS[source]}`, {
      method: "GET",
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) {
      const status = response.status === 401 ? 401 : response.status >= 500 ? 503 : 502;
      return NextResponse.json(
        { ok: false, code: status === 401 ? "upstream_authentication_failed" : "upstream_unavailable" },
        { status, headers: { "Cache-Control": "no-store" } },
      );
    }
    const body: unknown = await response.json();
    return NextResponse.json(body, {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        ...(response.headers.get("x-correlation-id")
          ? { "X-Correlation-ID": response.headers.get("x-correlation-id")! }
          : {}),
      },
    });
  } catch {
    return NextResponse.json(
      { ok: false, code: "upstream_unavailable" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

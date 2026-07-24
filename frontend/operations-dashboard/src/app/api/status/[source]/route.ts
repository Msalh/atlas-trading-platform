import { NextResponse } from "next/server";
import { readUpstream, type UpstreamSource } from "@/lib/upstream";

const SOURCES = new Set<UpstreamSource>([
  "health",
  "readiness",
  "latest",
  "operations",
]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ source: string }> },
) {
  const { source } = await context.params;
  if (!SOURCES.has(source as UpstreamSource)) {
    return NextResponse.json(
      { ok: false, code: "not_found" },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return readUpstream(source as UpstreamSource);
}

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "../route";

function makeRequest(path: string, query = ""): NextRequest {
  const url = `http://localhost:3000/api/proxy/${path}${query ? `?${query}` : ""}`;
  return new NextRequest(url);
}

function ctx(path: string) {
  return { params: Promise.resolve({ path: path.split("/") }) };
}

describe("GET /api/proxy/[...path]", () => {
  const originalFetch = global.fetch;
  const originalKey = process.env.ATLAS_API_KEY;

  beforeEach(() => {
    process.env.ATLAS_API_KEY = "the-real-secret-key";
  });

  afterEach(() => {
    global.fetch = originalFetch;
    process.env.ATLAS_API_KEY = originalKey;
    vi.restoreAllMocks();
  });

  it("rejects a path not on the allowlist without calling fetch", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await GET(makeRequest("trades"), ctx("trades"));
    expect(res.status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
    const body = await res.json();
    expect(body.ok).toBe(false);
  });

  it("forwards an allowed path with only its declared query params", async () => {
    let capturedUrl = "";
    global.fetch = vi.fn(async (url: string | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ ok: true, envelope: {}, report: {} }), { status: 200 });
    }) as unknown as typeof fetch;

    const res = await GET(
      makeRequest("research/re1/summary", "symbol=MNQ1!&unexpected=drop-me"),
      ctx("research/re1/summary"),
    );

    expect(res.status).toBe(200);
    expect(capturedUrl).toContain("/api/v1/research/re1/summary");
    expect(capturedUrl).not.toContain("unexpected");
    expect(capturedUrl).not.toContain("drop-me");
  });

  it("never forwards a browser-supplied Authorization header", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn(async (_url, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    const req = new NextRequest("http://localhost:3000/api/proxy/research/re1/summary", {
      headers: { Authorization: "Bearer browser-supplied-value" },
    });
    await GET(req, ctx("research/re1/summary"));

    expect(capturedHeaders?.get("Authorization")).toBe("Bearer the-real-secret-key");
    expect(capturedHeaders?.get("Authorization")).not.toContain("browser-supplied-value");
  });

  it("uses only the server-side ATLAS_API_KEY, never a value from the request", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn(async (_url, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    await GET(makeRequest("research/re1/summary", "api_key=not-the-real-key"), ctx("research/re1/summary"));
    expect(capturedHeaders?.get("Authorization")).toBe("Bearer the-real-secret-key");
  });

  it("passes through the upstream's own structured error body and status", async () => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify({ ok: false, error: "invalid symbol: too short" }), { status: 422 },
    )) as unknown as typeof fetch;

    const res = await GET(makeRequest("rule-engine/latest", "symbol=x&timeframe=5m"), ctx("rule-engine/latest"));
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.error).toBe("invalid symbol: too short");
  });

  it("returns a sanitized error, never a raw exception, on a network failure", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("connect ECONNREFUSED 10.0.0.5:8000 - internal hostname leak");
    }) as unknown as typeof fetch;

    const res = await GET(makeRequest("research/re1/summary"), ctx("research/re1/summary"));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("upstream request failed");
    expect(JSON.stringify(body)).not.toContain("ECONNREFUSED");
    expect(JSON.stringify(body)).not.toContain("10.0.0.5");
  });

  it("returns a sanitized error, never a stack trace, on a timeout", async () => {
    global.fetch = vi.fn(async () => {
      const err = new DOMException("The operation was aborted due to timeout", "TimeoutError");
      throw err;
    }) as unknown as typeof fetch;

    const res = await GET(makeRequest("research/re2/summary"), ctx("research/re2/summary"));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("upstream request failed");
  });

  it("never leaks the API key anywhere in a response body", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("boom");
    }) as unknown as typeof fetch;

    const res = await GET(makeRequest("setup-engine/latest", "symbol=MNQ1!&timeframe=5m"), ctx("setup-engine/latest"));
    const text = JSON.stringify(await res.json());
    expect(text).not.toContain("the-real-secret-key");
  });

  it("handles a non-JSON upstream response without crashing", async () => {
    global.fetch = vi.fn(async () => new Response("<html>not json</html>", { status: 200 })) as unknown as typeof fetch;
    const res = await GET(makeRequest("research/dataset-health"), ctx("research/dataset-health"));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.ok).toBe(false);
  });
});

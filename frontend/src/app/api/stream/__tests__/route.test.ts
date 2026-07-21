import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "../route";

function makeRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/stream");
}

describe("GET /api/stream", () => {
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

  it("calls the backend's /api/v1/stream with a server-side Authorization header, never a query param", async () => {
    let capturedUrl = "";
    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedHeaders = new Headers(init?.headers);
      return new Response(new ReadableStream(), {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    }) as unknown as typeof fetch;

    await GET(makeRequest());

    expect(capturedUrl).toBe("http://localhost:8000/api/v1/stream");
    expect(capturedUrl).not.toContain("api_key");
    expect(capturedHeaders?.get("Authorization")).toBe("Bearer the-real-secret-key");
  });

  it("streams the upstream response body without buffering it", async () => {
    const chunks = ["event: connected\ndata: {}\n\n", "event: trade\ndata: {}\n\n"];
    const upstreamStream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
        controller.close();
      },
    });
    global.fetch = vi.fn(async () => new Response(upstreamStream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    })) as unknown as typeof fetch;

    const res = await GET(makeRequest());

    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    expect(res.headers.get("Cache-Control")).toBe("no-cache");
    expect(res.headers.get("Connection")).toBe("keep-alive");

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let received = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      received += decoder.decode(value);
    }
    expect(received).toBe(chunks.join(""));
  });

  it("forwards the incoming request's AbortSignal to the upstream fetch", async () => {
    let capturedSignal: AbortSignal | undefined;
    global.fetch = vi.fn(async (_url: string | URL, init?: RequestInit) => {
      capturedSignal = init?.signal as AbortSignal;
      return new Response(new ReadableStream(), { status: 200 });
    }) as unknown as typeof fetch;

    const request = makeRequest();
    await GET(request);

    expect(capturedSignal).toBe(request.signal);
  });

  it("returns a sanitized 502, never a raw exception, on a network failure", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("connect ECONNREFUSED 10.0.0.5:8000 - internal hostname leak");
    }) as unknown as typeof fetch;

    const res = await GET(makeRequest());
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("upstream request failed");
    expect(JSON.stringify(body)).not.toContain("ECONNREFUSED");
    expect(JSON.stringify(body)).not.toContain("10.0.0.5");
  });

  it("never leaks ATLAS_API_KEY anywhere in a response body", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("boom");
    }) as unknown as typeof fetch;

    const res = await GET(makeRequest());
    const text = JSON.stringify(await res.json());
    expect(text).not.toContain("the-real-secret-key");
  });

  it("passes through the upstream status code (e.g. 401 if ATLAS_API_KEY is ever misconfigured)", async () => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify({ detail: "missing or invalid API key" }),
      { status: 401 },
    )) as unknown as typeof fetch;

    const res = await GET(makeRequest());
    expect(res.status).toBe(401);
  });
});

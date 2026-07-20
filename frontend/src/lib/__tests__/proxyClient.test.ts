import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

function isString(value: unknown): value is string {
  return typeof value === "string";
}

describe("proxyGet", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("returns the parsed body when the response is ok and passes validation", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify("hello"), { status: 200 })) as unknown as typeof fetch;
    const result = await proxyGet("research/re1/summary", {}, isString);
    expect(result).toBe("hello");
  });

  it("builds the request URL against the same-origin proxy with the given params", async () => {
    let capturedUrl = "";
    global.fetch = vi.fn(async (url: string | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify("ok"), { status: 200 });
    }) as unknown as typeof fetch;

    await proxyGet("rule-engine/latest", { symbol: "MNQU6", timeframe: "5m" }, isString);
    expect(capturedUrl).toBe("/api/proxy/rule-engine/latest?symbol=MNQU6&timeframe=5m");
  });

  it("omits the query string entirely when there are no params", async () => {
    let capturedUrl = "";
    global.fetch = vi.fn(async (url: string | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify("ok"), { status: 200 });
    }) as unknown as typeof fetch;

    await proxyGet("research/dataset-health", {}, isString);
    expect(capturedUrl).toBe("/api/proxy/research/dataset-health");
  });

  it("throws network_error when fetch itself rejects", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("boom");
    }) as unknown as typeof fetch;

    await expect(proxyGet("research/re1/summary", {}, isString)).rejects.toMatchObject({
      kind: "network_error",
    } satisfies Partial<ApiFetchError>);
  });

  it("throws invalid_response on a non-JSON body", async () => {
    global.fetch = vi.fn(async () => new Response("<html>", { status: 200 })) as unknown as typeof fetch;
    await expect(proxyGet("research/re1/summary", {}, isString)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("throws not_found on a 404 and surfaces the backend's own error text", async () => {
    global.fetch = vi.fn(
      async () => new Response(JSON.stringify({ ok: false, error: "not found" }), { status: 404 }),
    ) as unknown as typeof fetch;
    await expect(proxyGet("trades", {}, isString)).rejects.toMatchObject({
      kind: "not_found",
      message: "not found",
    });
  });

  it("throws invalid_request on a 422 with the backend's own error text", async () => {
    global.fetch = vi.fn(
      async () => new Response(JSON.stringify({ ok: false, error: "invalid symbol" }), { status: 422 }),
    ) as unknown as typeof fetch;
    await expect(proxyGet("rule-engine/latest", { symbol: "x" }, isString)).rejects.toMatchObject({
      kind: "invalid_request",
      message: "invalid symbol",
    });
  });

  it("throws upstream_error on a 502/503 with a generic message when the body has no error field", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: false }), { status: 503 })) as unknown as typeof fetch;
    await expect(proxyGet("research/dataset-health", {}, isString)).rejects.toMatchObject({
      kind: "upstream_error",
      message: "Unexpected response: HTTP 503",
    });
  });

  it("throws invalid_response when the ok response body fails the caller's validator", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify(42), { status: 200 })) as unknown as typeof fetch;
    await expect(proxyGet("research/re1/summary", {}, isString)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });
});

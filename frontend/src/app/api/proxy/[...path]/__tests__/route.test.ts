import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as routeModule from "../route";
import * as proxyAllowlist from "@/lib/proxyAllowlist";

const { GET, POST } = routeModule;

// Sprint 10 Slice A.1: research/promotion/decide (POST) was removed from
// production config - it belongs to Slice E, not this slice (see
// proxyAllowlist.ts's own comment). The POST mechanism itself (allowlist
// check, body-shape validation, field projection, forwarding) still needs
// real coverage, so these tests exercise it against this one local,
// clearly-named fixture path instead of a real production entry - spied
// onto isAllowedProxyMethod/projectAllowedBody so every OTHER path's real
// behavior (every GET test below) is completely unaffected.
const TEST_POST_PATH = "test-fixture/post-only";
const TEST_POST_FIELDS = ["hypothesis_id", "decision", "reviewer", "rationale", "evidence_snapshot_ref"];

// Captured once, before any vi.spyOn ever runs - vi.spyOn mutates the live
// module binding in place, so a mock implementation that calls
// `proxyAllowlist.isAllowedProxyMethod(...)` to "delegate to the real one"
// would actually be calling itself (infinite recursion). These two
// references are the one safe way to fall through to the real
// implementation from inside a mock of the same function.
const realIsAllowedProxyMethod = proxyAllowlist.isAllowedProxyMethod;
const realProjectAllowedBody = proxyAllowlist.projectAllowedBody;

function makeRequest(path: string, query = ""): NextRequest {
  const url = `http://localhost:3000/api/proxy/${path}${query ? `?${query}` : ""}`;
  return new NextRequest(url);
}

function makePostRequest(path: string, body: unknown): NextRequest {
  const url = `http://localhost:3000/api/proxy/${path}`;
  return new NextRequest(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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

  it("Slice A.1 regression: research/promotion/decide is no longer reachable via GET (it was never a GET path)", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await GET(makeRequest("research/promotion/decide"), ctx("research/promotion/decide"));
    expect(res.status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("POST /api/proxy/[...path]", () => {
  const originalFetch = global.fetch;
  const originalKey = process.env.ATLAS_API_KEY;
  let isAllowedProxyMethodSpy: ReturnType<typeof vi.spyOn>;
  let projectAllowedBodySpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    process.env.ATLAS_API_KEY = "the-real-secret-key";
    // Layer exactly one fixture path on top of the real allowlist behavior -
    // every path other than TEST_POST_PATH still resolves through the real,
    // unmodified isAllowedProxyMethod/projectAllowedBody.
    isAllowedProxyMethodSpy = vi.spyOn(proxyAllowlist, "isAllowedProxyMethod").mockImplementation((path, method, routes) => {
      if (path === TEST_POST_PATH && method === "POST") return true;
      return realIsAllowedProxyMethod(path, method, routes);
    });
    projectAllowedBodySpy = vi.spyOn(proxyAllowlist, "projectAllowedBody").mockImplementation((path, incoming, routes) => {
      if (path === TEST_POST_PATH) {
        const projected: Record<string, unknown> = {};
        for (const field of TEST_POST_FIELDS) {
          if (Object.prototype.hasOwnProperty.call(incoming, field)) projected[field] = incoming[field];
        }
        return projected;
      }
      return realProjectAllowedBody(path, incoming, routes);
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
    process.env.ATLAS_API_KEY = originalKey;
    isAllowedProxyMethodSpy.mockRestore();
    projectAllowedBodySpy.mockRestore();
    vi.restoreAllMocks();
  });

  it("rejects a path not on the allowlist without calling fetch", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await POST(makePostRequest("trades", {}), ctx("trades"));
    expect(res.status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("rejects POST on a path that only declares a GET config, without calling fetch", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await POST(makePostRequest("research/dataset-health", {}), ctx("research/dataset-health"));
    expect(res.status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("Slice A.1 regression: research/promotion/decide is no longer reachable via POST", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await POST(
      makePostRequest("research/promotion/decide", { hypothesis_id: "h1" }),
      ctx("research/promotion/decide"),
    );
    expect(res.status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("rejects a non-JSON-object body without calling fetch", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await POST(
      new NextRequest(`http://localhost:3000/api/proxy/${TEST_POST_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(["not", "an", "object"]),
      }),
      ctx(TEST_POST_PATH),
    );
    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("rejects a malformed (non-JSON) body without calling fetch", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    const res = await POST(
      new NextRequest(`http://localhost:3000/api/proxy/${TEST_POST_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "not json at all",
      }),
      ctx(TEST_POST_PATH),
    );
    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards only the declared body fields, dropping anything else", async () => {
    let capturedBody: unknown;
    global.fetch = vi.fn(async (_url, init?: RequestInit) => {
      capturedBody = JSON.parse(init?.body as string);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    await POST(
      makePostRequest(TEST_POST_PATH, {
        hypothesis_id: "h1", decision: "approved", reviewer: "jane", rationale: "clears the bar",
        evidence_snapshot_ref: "v1", realization_id: "attacker-supplied",
      }),
      ctx(TEST_POST_PATH),
    );

    expect(capturedBody).toEqual({
      hypothesis_id: "h1", decision: "approved", reviewer: "jane", rationale: "clears the bar",
      evidence_snapshot_ref: "v1",
    });
    expect(capturedBody).not.toHaveProperty("realization_id");
  });

  it("forwards to the correct upstream URL with a JSON content-type", async () => {
    let capturedUrl = "";
    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedHeaders = new Headers(init?.headers);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    await POST(makePostRequest(TEST_POST_PATH, { hypothesis_id: "h1" }), ctx(TEST_POST_PATH));
    expect(capturedUrl).toContain(`/api/v1/${TEST_POST_PATH}`);
    expect(capturedHeaders?.get("Content-Type")).toBe("application/json");
  });

  it("never forwards a browser-supplied Authorization header, using only the server-side key", async () => {
    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn(async (_url, init?: RequestInit) => {
      capturedHeaders = new Headers(init?.headers);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    const req = new NextRequest(`http://localhost:3000/api/proxy/${TEST_POST_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer browser-supplied-value" },
      body: JSON.stringify({ hypothesis_id: "h1" }),
    });
    await POST(req, ctx(TEST_POST_PATH));

    expect(capturedHeaders?.get("Authorization")).toBe("Bearer the-real-secret-key");
    expect(capturedHeaders?.get("Authorization")).not.toContain("browser-supplied-value");
  });

  it("passes through the upstream's own structured error body and status", async () => {
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify({ ok: false, error: "PromotionRecord requires a non-blank rationale" }), { status: 422 },
    )) as unknown as typeof fetch;

    const res = await POST(
      makePostRequest(TEST_POST_PATH, { hypothesis_id: "h1", rationale: "" }),
      ctx(TEST_POST_PATH),
    );
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.error).toBe("PromotionRecord requires a non-blank rationale");
  });

  it("returns a sanitized error, never a raw exception, on a network failure", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("connect ECONNREFUSED 10.0.0.5:8000 - internal hostname leak");
    }) as unknown as typeof fetch;

    const res = await POST(makePostRequest(TEST_POST_PATH, { hypothesis_id: "h1" }), ctx(TEST_POST_PATH));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("upstream request failed");
    expect(JSON.stringify(body)).not.toContain("ECONNREFUSED");
  });

  it("never leaks the API key anywhere in a response body", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("boom");
    }) as unknown as typeof fetch;

    const res = await POST(makePostRequest(TEST_POST_PATH, { hypothesis_id: "h1" }), ctx(TEST_POST_PATH));
    const text = JSON.stringify(await res.json());
    expect(text).not.toContain("the-real-secret-key");
  });

  it("handles a non-JSON upstream response without crashing", async () => {
    global.fetch = vi.fn(async () => new Response("<html>not json</html>", { status: 200 })) as unknown as typeof fetch;
    const res = await POST(makePostRequest(TEST_POST_PATH, { hypothesis_id: "h1" }), ctx(TEST_POST_PATH));
    expect(res.status).toBe(502);
  });
});

describe("access logging", () => {
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

  it("logs one line per GET request with method, path, and status - never a header, body, or the key", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })) as unknown as typeof fetch;
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    await GET(makeRequest("research/dataset-health"), ctx("research/dataset-health"));

    expect(logSpy).toHaveBeenCalledTimes(1);
    const line = logSpy.mock.calls[0][0] as string;
    expect(line).toContain("GET");
    expect(line).toContain("research/dataset-health");
    expect(line).toContain("200");
    expect(line).not.toContain("the-real-secret-key");
  });

  it("logs one line per successful POST request with method, path, and status", async () => {
    // Same test-fixture-path pattern as the POST describe block above - no
    // real production POST-allowed path exists yet (Slice E owns the first
    // one), so the success case is proven against a local fixture rather
    // than skipped or weakened into only testing a rejection.
    const isAllowedProxyMethodSpy = vi.spyOn(proxyAllowlist, "isAllowedProxyMethod").mockImplementation((path, method, routes) => {
      if (path === TEST_POST_PATH && method === "POST") return true;
      return realIsAllowedProxyMethod(path, method, routes);
    });
    const projectAllowedBodySpy = vi.spyOn(proxyAllowlist, "projectAllowedBody").mockImplementation((path, incoming, routes) => {
      if (path === TEST_POST_PATH) return { hypothesis_id: incoming.hypothesis_id };
      return realProjectAllowedBody(path, incoming, routes);
    });

    global.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 })) as unknown as typeof fetch;
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    await POST(makePostRequest(TEST_POST_PATH, { hypothesis_id: "h1" }), ctx(TEST_POST_PATH));

    expect(logSpy).toHaveBeenCalledTimes(1);
    const line = logSpy.mock.calls[0][0] as string;
    expect(line).toContain("POST");
    expect(line).toContain(TEST_POST_PATH);
    expect(line).toContain("200");
    expect(line).not.toContain("hypothesis_id");
    expect(line).not.toContain("the-real-secret-key");

    isAllowedProxyMethodSpy.mockRestore();
    projectAllowedBodySpy.mockRestore();
  });

  it("logs the rejection status for a POST to a path no longer on the allowlist (Slice A.1 regression)", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    await POST(makePostRequest("research/promotion/decide", { hypothesis_id: "h1" }), ctx("research/promotion/decide"));

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(logSpy).toHaveBeenCalledTimes(1);
    const line = logSpy.mock.calls[0][0] as string;
    expect(line).toContain("POST");
    expect(line).toContain("research/promotion/decide");
    expect(line).toContain("404");
    expect(line).not.toContain("hypothesis_id");
  });

  it("logs the rejection status for a disallowed path, without ever calling fetch", async () => {
    const fetchSpy = vi.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    await GET(makeRequest("trades"), ctx("trades"));

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(logSpy).toHaveBeenCalledTimes(1);
    expect(logSpy.mock.calls[0][0] as string).toContain("404");
  });
});

// Sprint 10 Slice A.1: verified empirically against a real `next dev` server
// (curl -X <method> against a live allowed path) rather than assumed from
// documentation - see docs/ui_v2/bff-proxy-architecture.md §8 for the exact
// observed responses. This route file exports only GET and POST; every other
// method's behavior below is entirely Next.js App Router's own framework
// behavior for a route file with that exact export set, not code this file
// implements - the test below is the one thing actually within this file's
// control: that no accidental handler for another method ever gets added
// without a deliberate decision.
describe("unhandled methods (framework-level behavior, verified empirically)", () => {
  it("exports exactly GET and POST - no PUT/PATCH/DELETE/HEAD/OPTIONS handler exists in this file", () => {
    // Verified live (next dev, curl): with only GET/POST exported, Next.js
    // itself returns 405 for PUT/PATCH/DELETE, auto-derives HEAD from GET
    // (mirrors GET's own status/allowlist behavior, empty body), and
    // auto-generates OPTIONS as 204 with `Allow: GET, HEAD, OPTIONS, POST`.
    // None of that is implemented here - if it ever needs to be (a future
    // slice legitimately requiring PUT/DELETE), it must be added as an
    // explicit, reviewed export, exactly like POST was in Slice A.
    const exported = Object.keys(routeModule).sort();
    expect(exported).toEqual(["GET", "POST"]);
  });
});

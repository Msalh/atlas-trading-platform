import { readUpstream } from "@/lib/upstream";

describe("server-only upstream boundary", () => {
  beforeEach(() => {
    process.env.TRADER_NOW_INTERNAL_URL = "http://private.internal";
    process.env.TRADER_NOW_API_KEY = "server-secret";
    vi.restoreAllMocks();
  });

  it("uses fixed GET-only routes and attaches the key server-side", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "X-Correlation-ID": "test-id" },
      }),
    );
    const response = await readUpstream("readiness");
    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://private.internal/readiness",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ Authorization: "Bearer server-secret" }),
        cache: "no-store",
      }),
    );
    expect(await response.text()).not.toContain("server-secret");
  });

  it("sanitizes upstream failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error("sensitive upstream infrastructure details"),
    );
    const response = await readUpstream("operations");
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ ok: false, code: "upstream_unavailable" });
  });

  it("preserves auth failure so the poller can stop", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "secret detail" }), { status: 401 }),
    );
    const response = await readUpstream("latest");
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ ok: false, code: "upstream_authentication_failed" });
  });
});

import {
  SYNTHETIC_CORRELATION_ID,
  SYNTHETIC_OPAQUE_CURSOR,
  SYNTHETIC_SNAPSHOT_ID,
  snapshotDetailFixture,
  snapshotErrorFixtures,
  snapshotIntegrityFixture,
  snapshotListFixture,
  snapshotMetadataFixture,
} from "../__fixtures__/snapshotApi";
import {
  readSnapshotDetail,
  readSnapshotIntegrity,
  readSnapshotList,
  readSnapshotMetadata,
} from "../server/snapshotReader";

function request(path: string, correlationId = SYNTHETIC_CORRELATION_ID) {
  return new Request(`http://dashboard.local${path}`, {
    headers: { "X-Correlation-ID": correlationId },
  });
}

function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("reader-only Snapshot API boundary", () => {
  beforeEach(() => {
    process.env.EVIDENCE_BROWSER_ENABLED = "true";
    process.env.SNAPSHOT_API_INTERNAL_URL = "http://snapshot-api.internal";
    process.env.SNAPSHOT_READER_API_TOKEN = "synthetic-reader-token";
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete process.env.EVIDENCE_BROWSER_ENABLED;
    delete process.env.SNAPSHOT_API_INTERNAL_URL;
    delete process.env.SNAPSHOT_READER_API_TOKEN;
  });

  it("fails closed for every route and repeated retry while disabled", async () => {
    process.env.EVIDENCE_BROWSER_ENABLED = "false";
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const responses = [
      await readSnapshotList(request("/api/evidence/snapshots")),
      await readSnapshotList(request("/api/evidence/snapshots")),
      await readSnapshotDetail(request("/detail"), SYNTHETIC_SNAPSHOT_ID),
      await readSnapshotMetadata(request("/metadata"), SYNTHETIC_SNAPSHOT_ID),
      await readSnapshotIntegrity(request("/integrity"), SYNTHETIC_SNAPSHOT_ID),
    ];
    for (const response of responses) {
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({
        ok: false,
        code: "evidence_browser_disabled",
        correlation_id: SYNTHETIC_CORRELATION_ID,
      });
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed for missing or unsafe server configuration", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    delete process.env.SNAPSHOT_READER_API_TOKEN;
    expect(
      (await readSnapshotList(request("/api/evidence/snapshots"))).status,
    ).toBe(503);
    process.env.SNAPSHOT_READER_API_TOKEN = "synthetic-reader-token";
    process.env.SNAPSHOT_API_INTERNAL_URL =
      "http://username:password@snapshot-api.internal/path";
    expect(
      (await readSnapshotList(request("/api/evidence/snapshots"))).status,
    ).toBe(503);
    process.env.SNAPSHOT_API_INTERNAL_URL = "http://snapshot-api.internal";
    for (const token of ["short", "synthetic token with spaces", "x\nunsafe"]) {
      process.env.SNAPSHOT_READER_API_TOKEN = token;
      expect(
        (await readSnapshotList(request("/api/evidence/snapshots"))).status,
      ).toBe(503);
    }
    process.env.SNAPSHOT_READER_API_TOKEN = "synthetic-reader-token";
    process.env.SNAPSHOT_API_INTERNAL_URL = " http://snapshot-api.internal";
    expect(
      (await readSnapshotList(request("/api/evidence/snapshots"))).status,
    ).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls the fixed list route with an opaque encoded cursor", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        jsonResponse(snapshotListFixture, 200, {
          "X-Correlation-ID": "upstream-correlation",
        }),
      );
    const response = await readSnapshotList(
      request(
        `/api/evidence/snapshots?limit=25&cursor=${encodeURIComponent(SYNTHETIC_OPAQUE_CURSOR)}`,
      ),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-correlation-id")).toBe(
      "upstream-correlation",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      `http://snapshot-api.internal/api/v1/snapshots?limit=25&cursor=${encodeURIComponent(SYNTHETIC_OPAQUE_CURSOR)}`,
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        redirect: "error",
        headers: expect.objectContaining({
          Accept: "application/json",
          Authorization: "Bearer synthetic-reader-token",
          "X-Correlation-ID": SYNTHETIC_CORRELATION_ID,
        }),
      }),
    );
    expect(await response.json()).toEqual(snapshotListFixture);
  });

  it("forwards only fixed headers and never arbitrary client headers", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(snapshotListFixture));
    await readSnapshotList(
      new Request("http://dashboard.local/api/evidence/snapshots", {
        headers: {
          "X-Correlation-ID": SYNTHETIC_CORRELATION_ID,
          Authorization: "Bearer client-controlled",
          Cookie: "private-cookie",
          "X-Arbitrary": "must-not-forward",
        },
      }),
    );
    const forwarded = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect([...forwarded.keys()].sort()).toEqual([
      "accept",
      "authorization",
      "x-correlation-id",
    ]);
    expect(forwarded.get("authorization")).toBe(
      "Bearer synthetic-reader-token",
    );
    expect(forwarded.get("cookie")).toBeNull();
    expect(forwarded.get("x-arbitrary")).toBeNull();
  });

  it("calls only fixed detail, metadata, and integrity routes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(snapshotDetailFixture))
      .mockResolvedValueOnce(jsonResponse(snapshotMetadataFixture))
      .mockResolvedValueOnce(jsonResponse(snapshotIntegrityFixture));
    expect(
      (await readSnapshotDetail(request("/detail"), SYNTHETIC_SNAPSHOT_ID))
        .status,
    ).toBe(200);
    expect(
      (await readSnapshotMetadata(request("/metadata"), SYNTHETIC_SNAPSHOT_ID))
        .status,
    ).toBe(200);
    expect(
      (await readSnapshotIntegrity(request("/integrity"), SYNTHETIC_SNAPSHOT_ID))
        .status,
    ).toBe(200);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      `http://snapshot-api.internal/api/v1/snapshots/${SYNTHETIC_SNAPSHOT_ID}`,
      `http://snapshot-api.internal/api/v1/snapshots/${SYNTHETIC_SNAPSHOT_ID}/metadata`,
      `http://snapshot-api.internal/api/v1/snapshots/${SYNTHETIC_SNAPSHOT_ID}/integrity`,
    ]);
  });

  it("rejects malformed IDs, cursor inputs, page sizes, and unknown parameters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    expect((await readSnapshotDetail(request("/detail"), "../capture")).status).toBe(
      400,
    );
    expect(
      (
        await readSnapshotList(
          request("/api/evidence/snapshots?limit=26"),
        )
      ).status,
    ).toBe(400);
    expect(
      (
        await readSnapshotList(
          request("/api/evidence/snapshots?cursor=one&cursor=two"),
        )
      ).status,
    ).toBe(400);
    expect(
      (
        await readSnapshotList(
          request("/api/evidence/snapshots?limit=25&limit=50"),
        )
      ).status,
    ).toBe(400);
    expect(
      (
        await readSnapshotList(
          request("/api/evidence/snapshots?capture=true"),
        )
      ).status,
    ).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sanitizes and translates upstream failures", async () => {
    const cases = [
      [400, 400, "invalid_snapshot_request"],
      [401, 502, "snapshot_upstream_authentication_failed"],
      [403, 502, "snapshot_upstream_authorization_failed"],
      [404, 404, "snapshot_not_found"],
      [409, 409, "snapshot_integrity_failed"],
      [429, 429, "snapshot_rate_limited"],
      [503, 503, "snapshot_service_unavailable"],
    ] as const;
    for (const [upstream, expected, code] of cases) {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        jsonResponse(snapshotErrorFixtures.unavailable, upstream, {
          "X-Internal-Secret": "must-not-forward",
          "Retry-After": upstream === 429 ? "12" : "unsafe",
        }),
      );
      const response = await readSnapshotList(
        request("/api/evidence/snapshots"),
      );
      expect(response.status).toBe(expected);
      expect((await response.json()).code).toBe(code);
      expect(response.headers.get("x-internal-secret")).toBeNull();
      expect(response.headers.get("retry-after")).toBe(
        upstream === 429 ? "12" : null,
      );
    }
  });

  it("rejects malformed, unsupported, non-JSON, and oversized success responses", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ...snapshotListFixture, schema_version: "unknown.v1" }),
    );
    expect(
      (await readSnapshotList(request("/api/evidence/snapshots"))).status,
    ).toBe(502);

    fetchMock.mockResolvedValueOnce(
      new Response("not json", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      }),
    );
    const nonJson = await readSnapshotList(
      request("/api/evidence/snapshots"),
    );
    expect(nonJson.status).toBe(502);
    expect((await nonJson.json()).code).toBe(
      "unexpected_snapshot_response",
    );

    fetchMock.mockResolvedValueOnce(
      new Response("{}", {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": String(513 * 1024),
        },
      }),
    );
    const oversized = await readSnapshotList(
      request("/api/evidence/snapshots"),
    );
    expect(oversized.status).toBe(502);
    expect((await oversized.json()).code).toBe(
      "snapshot_response_too_large",
    );

    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ...snapshotListFixture,
        ok: false,
        code: "snapshot_integrity_failed",
      }),
    );
    const hybrid = await readSnapshotList(
      request("/api/evidence/snapshots"),
    );
    expect(hybrid.status).toBe(502);
    expect((await hybrid.json()).code).toBe("unexpected_snapshot_response");

    fetchMock.mockResolvedValueOnce(
      new Response("{", {
        headers: { "Content-Type": "application/json" },
      }),
    );
    const malformedJson = await readSnapshotList(
      request("/api/evidence/snapshots"),
    );
    expect(malformedJson.status).toBe(502);
    expect((await malformedJson.json()).code).toBe(
      "unexpected_snapshot_response",
    );
  });

  it.each([
    ["detail", 5 * 1024 * 1024 + 1, readSnapshotDetail],
    ["metadata", 256 * 1024 + 1, readSnapshotMetadata],
    ["integrity", 64 * 1024 + 1, readSnapshotIntegrity],
  ])("enforces the %s response-size policy", async (
    _kind,
    contentLength,
    reader,
  ) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", {
        headers: {
          "Content-Type": "application/json",
          "Content-Length": String(contentLength),
        },
      }),
    );
    const response = await reader(request("/reader"), SYNTHETIC_SNAPSHOT_ID);
    expect(response.status).toBe(502);
    expect((await response.json()).code).toBe("snapshot_response_too_large");
  });

  it("cleans up the upstream timeout and parent abort listener after success", async () => {
    vi.useFakeTimers();
    try {
      const dashboardRequest = request("/api/evidence/snapshots");
      const removeListener = vi.spyOn(
        dashboardRequest.signal,
        "removeEventListener",
      );
      let upstreamSignal: AbortSignal | undefined;
      vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
        upstreamSignal = init?.signal ?? undefined;
        return jsonResponse(snapshotListFixture);
      });

      expect((await readSnapshotList(dashboardRequest)).status).toBe(200);
      vi.advanceTimersByTime(10_000);
      expect(upstreamSignal?.aborted).toBe(false);
      expect(removeListener).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("distinguishes bounded timeout from caller cancellation", async () => {
    vi.useFakeTimers();
    try {
      vi.spyOn(globalThis, "fetch").mockImplementation(
        (_url, init) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener(
              "abort",
              () => reject(init.signal?.reason),
              { once: true },
            );
          }),
      );
      const timedOut = readSnapshotList(request("/api/evidence/snapshots"));
      await vi.advanceTimersByTimeAsync(3_001);
      const timeoutResponse = await timedOut;
      expect(timeoutResponse.status).toBe(504);
      expect((await timeoutResponse.json()).code).toBe(
        "snapshot_upstream_timeout",
      );

      const controller = new AbortController();
      const cancelled = readSnapshotList(
        new Request("http://dashboard.local/api/evidence/snapshots", {
          signal: controller.signal,
          headers: { "X-Correlation-ID": SYNTHETIC_CORRELATION_ID },
        }),
      );
      controller.abort();
      const cancelledResponse = await cancelled;
      expect(cancelledResponse.status).toBe(499);
      expect((await cancelledResponse.json()).code).toBe(
        "snapshot_request_cancelled",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("rejects a successful response for a different snapshot identity", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ...snapshotMetadataFixture,
        snapshot_id: "019b1111-2222-7333-8444-666666666666",
      }),
    );
    const response = await readSnapshotMetadata(
      request("/metadata"),
      SYNTHETIC_SNAPSHOT_ID,
    );
    expect(response.status).toBe(502);
    expect((await response.json()).code).toBe(
      "unexpected_snapshot_response",
    );
  });

  it("never returns the reader token or raw infrastructure failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error(
        "synthetic-reader-token at postgres://private-database.internal",
      ),
    );
    const response = await readSnapshotList(
      request("/api/evidence/snapshots"),
    );
    const body = await response.text();
    expect(response.status).toBe(503);
    expect(body).not.toContain("synthetic-reader-token");
    expect(body).not.toContain("postgres");
    expect(body).not.toContain("private-database");
  });
});

import {
  LOCAL_RESPONSE_LIMITS,
  LocalResponseError,
  hasErrorEnvelopeMarkers,
  readBoundedJson,
  safeErrorCode,
} from "../clientTransport";

function response(
  body: string,
  contentType = "application/json",
  headers: Record<string, string> = {},
) {
  return new Response(body, {
    headers: { "Content-Type": contentType, ...headers },
  });
}

describe("local Evidence BFF transport hardening", () => {
  it("parses bounded JSON and rejects unexpected content or malformed JSON", async () => {
    await expect(
      readBoundedJson(response('{"safe":true}'), 1024),
    ).resolves.toEqual({ safe: true });
    await expect(
      readBoundedJson(response("{}", "text/plain"), 1024),
    ).rejects.toEqual(new LocalResponseError("unexpected_content_type"));
    await expect(
      readBoundedJson(response("{"), 1024),
    ).rejects.toEqual(new LocalResponseError("malformed_json"));
  });

  it("rejects declared and actual oversized responses before use", async () => {
    await expect(
      readBoundedJson(
        response("{}", "application/json", {
          "Content-Length": String(LOCAL_RESPONSE_LIMITS.integrity + 1),
        }),
        LOCAL_RESPONSE_LIMITS.integrity,
      ),
    ).rejects.toEqual(new LocalResponseError("response_too_large"));
    await expect(
      readBoundedJson(
        response(JSON.stringify({ value: "x".repeat(1024) })),
        128,
      ),
    ).rejects.toEqual(new LocalResponseError("response_too_large"));
  });

  it("accepts only the exact sanitized BFF error envelope", async () => {
    await expect(
      safeErrorCode(
        new Response(
          JSON.stringify({
            ok: false,
            code: "snapshot_upstream_timeout",
            correlation_id: "synthetic-correlation",
          }),
          { status: 504, headers: { "Content-Type": "application/json" } },
        ),
        "safe_fallback",
      ),
    ).resolves.toBe("snapshot_upstream_timeout");

    for (const body of [
      {
        ok: false,
        code: "snapshot_integrity_failed",
        correlation_id: "synthetic",
        message: "unexpected hybrid field",
      },
      {
        ok: true,
        code: "snapshot_integrity_failed",
        correlation_id: "synthetic",
      },
      {
        ok: false,
        code: "UNSAFE CODE",
        correlation_id: "synthetic",
      },
    ]) {
      await expect(
        safeErrorCode(
          new Response(JSON.stringify(body), {
            status: 502,
            headers: { "Content-Type": "application/json" },
          }),
          "safe_fallback",
        ),
      ).resolves.toBe("safe_fallback");
    }
  });

  it("handles non-JSON dashboard authentication without exposing its body", async () => {
    await expect(
      safeErrorCode(
        new Response("private host and stack details", {
          status: 401,
          headers: { "Content-Type": "text/plain" },
        }),
        "safe_fallback",
      ),
    ).resolves.toBe("dashboard_authentication_required");
  });

  it("detects success/error hybrid markers", () => {
    expect(hasErrorEnvelopeMarkers({ schema_version: "v1", ok: false })).toBe(
      true,
    );
    expect(hasErrorEnvelopeMarkers({ schema_version: "v1", snapshot: {} })).toBe(
      false,
    );
  });
});

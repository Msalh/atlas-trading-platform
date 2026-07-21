import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchDatasetHealth, fetchRe1Summary, fetchRe2Summary } from "@/lib/researchApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const frozenEnvelope = {
  schema_version: "1.0",
  source_track: "frozen",
  symbol: "MNQU6",
  timeframe: "5m",
  generated_at: "2026-07-20T00:00:00Z",
  data_as_of: "2026-06-01T00:00:00Z",
  code_version: "a907325fbb357097fb0e8e064d46772e2b719964",
  warnings: [] as string[],
};

describe("fetchRe1Summary / fetchRe2Summary", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses envelope + report and shows source_computation_version as code_version", async () => {
    mockFetchOnce({ ok: true, envelope: frozenEnvelope, report: { deliverables: [] } });
    const result = await fetchRe1Summary();
    expect(result.envelope.code_version).toBe("a907325fbb357097fb0e8e064d46772e2b719964");
    expect(result.envelope.source_track).toBe("frozen");
  });

  it("accepts an arbitrary report payload shape without narrowing it", async () => {
    mockFetchOnce({ ok: true, envelope: frozenEnvelope, report: { anything: "goes", nested: { a: 1 } } });
    const result = await fetchRe2Summary();
    expect(result.report).toEqual({ anything: "goes", nested: { a: 1 } });
  });

  it("throws upstream_error when the snapshot file is missing (503)", async () => {
    mockFetchOnce({ ok: false, error: "re1-summary.v1.json does not exist" }, 503);
    await expect(fetchRe1Summary()).rejects.toMatchObject({ kind: "upstream_error" });
  });

  it("rejects a response missing its envelope", async () => {
    mockFetchOnce({ ok: true, report: {} });
    await expect(fetchRe1Summary()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchDatasetHealth", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function validBody() {
    return {
      ok: true,
      envelope: frozenEnvelope,
      dataset_identity: {
        symbol: "MNQU6",
        timeframe: "5m",
        row_count: 97858,
        date_range: { start: "2024-01-01", end: "2026-06-01" },
      },
      segment_count: 12,
      certification: {
        checks_run: 20,
        pass_count: 18,
        warning_count: 2,
        fail_count: 0,
        verdict: "certified_with_warnings",
        checks: [{ section: "Gap detection", check: "no gap exceeds 1.5x", verdict: "WARNING", detail: "2 gaps found" }],
      },
      known_warnings: [
        {
          id: "volume_ratio_caveat",
          severity: "warning",
          title: "volume_ratio caveat",
          detail: "some detail",
          source_document: "docs/market_engine/re2-freeze.md",
          source_section: "§3.2",
        },
      ],
      frozen_version: {
        source_computation_version: "806e4f1ae2386a68207192089ab303d77c05fa66",
        exported_at: "2026-07-20T00:00:00Z",
      },
    };
  }

  it("parses a well-formed dataset-health response", async () => {
    mockFetchOnce(validBody());
    const result = await fetchDatasetHealth();
    expect(result.certification.verdict).toBe("certified_with_warnings");
    expect(result.known_warnings[0].source_document).toBe("docs/market_engine/re2-freeze.md");
    expect(result.frozen_version.source_computation_version).toBe("806e4f1ae2386a68207192089ab303d77c05fa66");
  });

  it("rejects a known_warnings entry missing source_section", async () => {
    const body = validBody();
    // @ts-expect-error - intentionally malformed for the test
    delete body.known_warnings[0].source_section;
    mockFetchOnce(body);
    await expect(fetchDatasetHealth()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("rejects a certification summary with a non-array checks field", async () => {
    const body = validBody();
    // @ts-expect-error - intentionally malformed for the test
    body.certification.checks = "not-an-array";
    mockFetchOnce(body);
    await expect(fetchDatasetHealth()).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

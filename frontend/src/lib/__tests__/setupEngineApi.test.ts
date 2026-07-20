import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchLatestSetupEngineOutput, fetchLiveEpisodes } from "@/lib/setupEngineApi";

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

const envelope = {
  schema_version: "1.0",
  source_track: "live",
  symbol: "MNQU6",
  timeframe: "5m",
  generated_at: "2026-07-20T12:00:00Z",
  data_as_of: "2026-07-20T11:55:00Z",
  code_version: "abc123",
  warnings: [] as string[],
};

const factSnapshot = {
  volume_spike: true,
  displacement: false,
  rejection: null,
  trend_5m: "up",
  liquidity_sweep: false,
  reclaim: null,
  vwap_relationship: "above",
};

describe("fetchLatestSetupEngineOutput", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("parses a found=true response with a computed and an insufficient_data setup", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      envelope,
      data: {
        schema_version: "1.0",
        symbol: "MNQU6",
        timeframe: "5m",
        occurred_at: "2026-07-20T11:55:00Z",
        setups: [
          {
            name: "displacement_reclaim",
            status: "computed",
            detected: true,
            severity: "strong",
            definition_version: "1.0",
            evidence: { supporting_facts: [{ fact_name: "displacement", occurred_at: "t", value: true, detail: {} }] },
          },
          {
            name: "liquidity_sweep_reversal",
            status: "insufficient_data",
            definition_version: "1.0",
            reason: "not enough history",
          },
        ],
      },
    });

    const result = await fetchLatestSetupEngineOutput("MNQU6", "5m");
    expect(result.found).toBe(true);
    expect(result.data?.setups).toHaveLength(2);
    expect(result.data?.setups[0].status).toBe("computed");
    expect(result.data?.setups[1].status).toBe("insufficient_data");
  });

  it("parses a found=false response without requiring an envelope", async () => {
    mockFetchOnce({ ok: true, found: false, data: null });
    const result = await fetchLatestSetupEngineOutput("MNQU6", "5m");
    expect(result.found).toBe(false);
    expect(result.data).toBeNull();
  });

  it("rejects a response missing evidence.supporting_facts on a computed setup", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      envelope,
      data: {
        schema_version: "1.0",
        symbol: "MNQU6",
        timeframe: "5m",
        occurred_at: "t",
        setups: [{ name: "x", status: "computed", detected: true, severity: null, definition_version: "1.0", evidence: {} }],
      },
    });
    await expect(fetchLatestSetupEngineOutput("MNQU6", "5m")).rejects.toMatchObject({ kind: "invalid_response" });
  });
});

describe("fetchLiveEpisodes", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  function activeEpisode() {
    return {
      setup_name: "displacement_reclaim",
      left_boundary_reason: "query_window_start",
      activation_timestamp_observed: null,
      observed_start_timestamp: "2026-07-20T10:00:00Z",
      duration_bars_observed: 12,
      is_window_truncated: true,
      is_active: true,
      last_observed_timestamp: "2026-07-20T11:55:00Z",
      end_timestamp_observed: null,
      termination_reason: null,
      right_boundary_observed: false,
      is_continuation: false,
      start_state: factSnapshot,
      end_state: factSnapshot,
    };
  }

  it("parses a found=true live-episodes response with an active episode", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      envelope,
      window: { requested: 500, actually_used: 500 },
      setups: {
        displacement_reclaim: {
          current_episode: activeEpisode(),
          recent_episodes: [],
          computability: {
            computable_bars: 450,
            non_computable_bars: 50,
            detected_true_bars: 10,
            detected_false_bars: 440,
            insufficient_reason_counts: {},
          },
        },
      },
      segments: [{ segment_id: "seg-1", start_timestamp: "t0", end_timestamp: null }],
      activation_events: [{ timestamp: "t1", segment_id: "seg-1", activated_setups: ["displacement_reclaim"] }],
    });

    const result = await fetchLiveEpisodes("MNQU6", "5m", 500);
    expect(result.found).toBe(true);
    if (!result.found) throw new Error("expected found=true");
    expect(result.setups.displacement_reclaim.current_episode?.is_active).toBe(true);
    expect(result.setups.displacement_reclaim.current_episode?.end_timestamp_observed).toBeNull();
  });

  it("parses a found=false response", async () => {
    mockFetchOnce({ ok: true, found: false, data: null });
    const result = await fetchLiveEpisodes("MNQU6", "5m");
    expect(result.found).toBe(false);
  });

  it("validates shape only, not cross-field invariants already enforced server-side", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      envelope,
      window: { requested: 500, actually_used: 500 },
      setups: {
        displacement_reclaim: {
          current_episode: { ...activeEpisode(), end_timestamp_observed: "2026-07-20T11:55:00Z" },
          recent_episodes: [],
          computability: {
            computable_bars: 1,
            non_computable_bars: 0,
            detected_true_bars: 0,
            detected_false_bars: 1,
            insufficient_reason_counts: {},
          },
        },
      },
      segments: [],
      activation_events: [],
    });

    // The client's runtime guard only checks shape, not cross-field
    // invariants (the backend dataclass's own __post_init__ already enforces
    // those before serialization) - this still parses. Documented here so a
    // future stricter guard is a deliberate choice, not an oversight.
    const result = await fetchLiveEpisodes("MNQU6", "5m");
    expect(result.found).toBe(true);
  });

  it("includes window as a query param only when provided", async () => {
    let capturedUrl = "";
    global.fetch = vi.fn(async (url: string | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ ok: true, found: false, data: null }), { status: 200 });
    }) as unknown as typeof fetch;

    await fetchLiveEpisodes("MNQU6", "5m");
    expect(capturedUrl).not.toContain("window");

    await fetchLiveEpisodes("MNQU6", "5m", 250);
    expect(capturedUrl).toContain("window=250");
  });
});

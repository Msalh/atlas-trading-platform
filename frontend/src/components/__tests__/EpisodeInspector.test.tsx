import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EpisodeInspector } from "@/components/EpisodeInspector";
import { LiveSelectorProvider } from "@/lib/liveSelector";

function renderInspector() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LiveSelectorProvider>
        <EpisodeInspector />
      </LiveSelectorProvider>
    </QueryClientProvider>,
  );
}

const factSnapshot = {
  volume_spike: true,
  displacement: true,
  rejection: null,
  trend_5m: "up",
  liquidity_sweep: false,
  reclaim: null,
  vwap_relationship: "above",
};

function liveEnvelope(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "1.0",
    source_track: "live",
    symbol: "MNQU6",
    timeframe: "5m",
    generated_at: "t",
    data_as_of: "t",
    code_version: "abc",
    warnings: [],
    ...overrides,
  };
}

function frozenEnvelope(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "1.0",
    source_track: "frozen",
    symbol: "MNQ1!",
    timeframe: "5m",
    generated_at: "t",
    data_as_of: "t",
    code_version: "806e4f1",
    warnings: [],
    ...overrides,
  };
}

function activeEpisode() {
  return {
    setup_name: "displacement_reclaim",
    segment_id: "seg-1",
    left_boundary_reason: "observed_activation",
    activation_timestamp_observed: "2026-07-20T11:00:00Z",
    observed_start_timestamp: "2026-07-20T11:00:00Z",
    duration_bars_observed: 12,
    is_window_truncated: false,
    is_active: true,
    last_observed_timestamp: "2026-07-20T11:55:00Z",
    end_timestamp_observed: null,
    termination_reason: null,
    right_boundary_observed: false,
    is_continuation: true,
    start_state: factSnapshot,
    end_state: factSnapshot,
  };
}

function closedEpisode(overrides: Record<string, unknown> = {}) {
  return {
    setup_name: "displacement_reclaim",
    segment_id: "seg-0",
    left_boundary_reason: "observed_activation",
    activation_timestamp_observed: "2026-07-20T09:00:00Z",
    observed_start_timestamp: "2026-07-20T09:00:00Z",
    duration_bars_observed: 6,
    is_window_truncated: false,
    is_active: false,
    last_observed_timestamp: "2026-07-20T09:30:00Z",
    end_timestamp_observed: "2026-07-20T09:30:00Z",
    termination_reason: "became_false",
    right_boundary_observed: true,
    is_continuation: false,
    start_state: factSnapshot,
    end_state: factSnapshot,
    ...overrides,
  };
}

function liveBody(currentEpisode: unknown, recentEpisodes: unknown[] = [], liveSymbol = "MNQU6") {
  return {
    ok: true,
    found: true,
    envelope: liveEnvelope({ symbol: liveSymbol }),
    window: { requested: 500, actually_used: 500 },
    setups: {
      displacement_reclaim: {
        current_episode: currentEpisode,
        recent_episodes: recentEpisodes,
        computability: { computable_bars: 1, non_computable_bars: 0, detected_true_bars: 1, detected_false_bars: 0, insufficient_reason_counts: {} },
      },
    },
    segments: [],
    activation_events: [],
  };
}

function re2Body(frozenSymbol = "MNQ1!") {
  return {
    ok: true,
    envelope: frozenEnvelope({ symbol: frozenSymbol }),
    report: {
      setup_profile: {
        entries: [
          {
            setup_name: "displacement_reclaim",
            episode_count: 100,
            all_episodes_duration: { count: 100, max: 10, mean: 2, median: 1, p75: 2, p90: 3, p95: 4 },
            fully_observed_duration: { count: 95, max: 10, mean: 2, median: 1, p75: 2, p90: 3, p95: 4 },
          },
        ],
      },
    },
  };
}

function mockFetch(handlers: { live: unknown; re2: unknown }) {
  global.fetch = vi.fn(async (url: string | URL) => {
    const u = String(url);
    if (u.includes("episodes/live")) return new Response(JSON.stringify(handlers.live), { status: 200 });
    if (u.includes("re2/summary")) return new Response(JSON.stringify(handlers.re2), { status: 200 });
    throw new Error(`unexpected URL ${u}`);
  }) as unknown as typeof fetch;
}

describe("EpisodeInspector", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("keeps the live current-episode panel and the frozen distribution panel visually distinct", async () => {
    // lib/liveSelector.tsx's default live symbol is MNQU6 - matching the
    // frozen envelope's symbol here so no mismatch is in play for this test.
    mockFetch({ live: liveBody(activeEpisode()), re2: re2Body("MNQU6") });
    renderInspector();
    await waitFor(() => expect(screen.getByText("Active through last closed bar.")).toBeInTheDocument());
    expect(screen.getByText("Current Episode (Live)")).toBeInTheDocument();
    expect(screen.getByText("Historical Duration Distribution (Frozen)")).toBeInTheDocument();
    expect(screen.getByText(/Historical comparison across 95 episodes/)).toBeInTheDocument();
  });

  it("hides the historical distribution entirely and shows the exact mismatch banner on a symbol mismatch", async () => {
    mockFetch({ live: liveBody(activeEpisode(), [], "ESU6"), re2: re2Body("MNQ1!") });
    renderInspector();
    await waitFor(() => expect(screen.getByText("Current Episode (Live)")).toBeInTheDocument());
    // ESU6 is the app default's live symbol only if set - here the live
    // selector defaults to MNQU6, but the live body's envelope carries the
    // mismatched symbol only for context; the mismatch check compares the
    // FROZEN identity (MNQ1!) against the actual live selector (MNQU6) -
    // both differ, so the banner must show.
    await waitFor(() => expect(screen.getByText("Frozen research baseline is available for MNQ1! / 5m.")).toBeInTheDocument());
    expect(screen.queryByText(/Historical comparison across/)).not.toBeInTheDocument();
  });

  it("shows a real termination_reason and end_timestamp_observed for recent closed episodes", async () => {
    mockFetch({ live: liveBody(null, [closedEpisode()]), re2: re2Body() });
    renderInspector();
    await waitFor(() => expect(screen.getByText("Ended: the condition became false.")).toBeInTheDocument());
  });

  it("shows a neutral not-active message when the selected setup has no current episode", async () => {
    mockFetch({ live: liveBody(null), re2: re2Body() });
    renderInspector();
    await waitFor(() => expect(screen.getByText("displacement_reclaim is not currently active.")).toBeInTheDocument());
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActiveSetupBundle } from "@/components/ActiveSetupBundle";
import { LiveSelectorProvider } from "@/lib/liveSelector";

function renderBundle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LiveSelectorProvider>
        <ActiveSetupBundle />
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

function baseEpisode(overrides: Record<string, unknown> = {}) {
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
    ...overrides,
  };
}

function bodyWithEpisode(episode: Record<string, unknown>) {
  return {
    ok: true,
    found: true,
    envelope: {
      schema_version: "1.0",
      source_track: "live",
      symbol: "MNQU6",
      timeframe: "5m",
      generated_at: "2026-07-20T12:00:00Z",
      data_as_of: "2026-07-20T11:55:00Z",
      code_version: "abc123",
      warnings: [],
    },
    window: { requested: 500, actually_used: 500 },
    setups: {
      displacement_reclaim: {
        current_episode: episode,
        recent_episodes: [],
        computability: { computable_bars: 1, non_computable_bars: 0, detected_true_bars: 1, detected_false_bars: 0, insufficient_reason_counts: {} },
      },
    },
    segments: [],
    activation_events: [],
  };
}

function mockFetchOnce(body: unknown) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })) as unknown as typeof fetch;
}

describe("ActiveSetupBundle", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows the real activation timestamp when observed_activation resolves the left boundary", async () => {
    mockFetchOnce(bodyWithEpisode(baseEpisode()));
    renderBundle();
    await waitFor(() => expect(screen.getByText(/Activated at/)).toBeInTheDocument());
    expect(screen.getByText("Active through last closed bar.")).toBeInTheDocument();
  });

  it("shows the query_window_start copy and never a false-precision timestamp", async () => {
    mockFetchOnce(
      bodyWithEpisode(
        baseEpisode({ left_boundary_reason: "query_window_start", activation_timestamp_observed: null, is_window_truncated: true, duration_bars_observed: 40 }),
      ),
    );
    renderBundle();
    await waitFor(() =>
      expect(
        screen.getByText("Active for at least 40 bars — activation occurred before the loaded window."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Activated at/)).not.toBeInTheDocument();
  });

  it("shows the segment_start copy distinctly from query_window_start", async () => {
    mockFetchOnce(
      bodyWithEpisode(baseEpisode({ left_boundary_reason: "segment_start", activation_timestamp_observed: null, duration_bars_observed: 5 })),
    );
    renderBundle();
    await waitFor(() =>
      expect(
        screen.getByText("Active for at least 5 bars — activation occurred before available data begins."),
      ).toBeInTheDocument(),
    );
  });

  it("never renders end_timestamp_observed or a termination reason for an active episode", async () => {
    mockFetchOnce(bodyWithEpisode(baseEpisode()));
    renderBundle();
    await waitFor(() => expect(screen.getByText("Active through last closed bar.")).toBeInTheDocument());
    expect(screen.queryByText(/became_false|insufficient_data|segment_end/)).not.toBeInTheDocument();
  });

  it("shows a neutral empty state when no setup is currently active", async () => {
    mockFetchOnce({
      ok: true,
      found: true,
      envelope: {
        schema_version: "1.0",
        source_track: "live",
        symbol: "MNQU6",
        timeframe: "5m",
        generated_at: "t",
        data_as_of: "t",
        code_version: "abc",
        warnings: [],
      },
      window: { requested: 500, actually_used: 500 },
      setups: {
        displacement_reclaim: {
          current_episode: null,
          recent_episodes: [],
          computability: { computable_bars: 1, non_computable_bars: 0, detected_true_bars: 0, detected_false_bars: 1, insufficient_reason_counts: {} },
        },
      },
      segments: [],
      activation_events: [],
    });
    renderBundle();
    await waitFor(() => expect(screen.getByText("No setups are currently active.")).toBeInTheDocument());
  });
});

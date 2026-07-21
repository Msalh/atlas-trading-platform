import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Timeline } from "@/components/Timeline";
import { LiveSelectorProvider } from "@/lib/liveSelector";

function renderTimeline() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LiveSelectorProvider>
        <Timeline />
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

function closedEpisode(overrides: Record<string, unknown> = {}) {
  return {
    setup_name: "displacement_reclaim",
    segment_id: "seg-1",
    left_boundary_reason: "observed_activation",
    activation_timestamp_observed: "2026-07-20T09:00:00Z",
    observed_start_timestamp: "2026-07-20T09:00:00Z",
    duration_bars_observed: 8,
    is_window_truncated: false,
    is_active: false,
    last_observed_timestamp: "2026-07-20T09:40:00Z",
    end_timestamp_observed: "2026-07-20T09:40:00Z",
    termination_reason: "became_false",
    right_boundary_observed: true,
    is_continuation: false,
    start_state: factSnapshot,
    end_state: factSnapshot,
    ...overrides,
  };
}

function openEpisode(overrides: Record<string, unknown> = {}) {
  return {
    setup_name: "displacement_reclaim",
    segment_id: "seg-2",
    left_boundary_reason: "query_window_start",
    activation_timestamp_observed: null,
    observed_start_timestamp: "2026-07-20T11:00:00Z",
    duration_bars_observed: 12,
    is_window_truncated: true,
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

function body(recentEpisodes: Record<string, unknown>[], currentEpisode: Record<string, unknown> | null, activationEvents: Record<string, unknown>[] = []) {
  return {
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
        current_episode: currentEpisode,
        recent_episodes: recentEpisodes,
        computability: { computable_bars: 1, non_computable_bars: 0, detected_true_bars: 1, detected_false_bars: 0, insufficient_reason_counts: {} },
      },
    },
    segments: [],
    activation_events: activationEvents,
  };
}

function mockFetchOnce(responseBody: unknown) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(responseBody), { status: 200 })) as unknown as typeof fetch;
}

describe("Timeline", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("distinguishes an observed left edge from an unresolved one, and a closed right edge from an open one", async () => {
    mockFetchOnce(body([closedEpisode()], openEpisode()));
    renderTimeline();
    await waitFor(() => expect(screen.getByText("displacement_reclaim")).toBeInTheDocument());

    const blocks = document.querySelectorAll("[data-left-edge]");
    expect(blocks).toHaveLength(2);
    const leftEdges = Array.from(blocks).map((b) => b.getAttribute("data-left-edge"));
    expect(leftEdges).toContain("observed");
    expect(leftEdges).toContain("unresolved");

    const rightEdges = Array.from(blocks).map((b) => b.getAttribute("data-right-edge"));
    expect(rightEdges).toContain("closed");
    expect(rightEdges).toContain("open");
  });

  it("renders an explicit gap marker between two episodes in different segments", async () => {
    mockFetchOnce(body([closedEpisode({ segment_id: "seg-1" })], openEpisode({ segment_id: "seg-2" })));
    renderTimeline();
    await waitFor(() => expect(screen.getByTestId("gap-marker")).toBeInTheDocument());
  });

  it("does not render a gap marker within the same segment", async () => {
    mockFetchOnce(body([closedEpisode({ segment_id: "seg-1", observed_start_timestamp: "2026-07-20T08:00:00Z" })], openEpisode({ segment_id: "seg-1" })));
    renderTimeline();
    await waitFor(() => expect(screen.getByText("displacement_reclaim")).toBeInTheDocument());
    expect(screen.queryByTestId("gap-marker")).not.toBeInTheDocument();
  });

  it("renders a simultaneous multi-setup ActivationEvent as one combined label, never split rows implying order", async () => {
    mockFetchOnce(
      body([], null, [
        { timestamp: "2026-07-20T11:00:00Z", segment_id: "seg-2", activated_setups: ["displacement_reclaim", "vwap_extension"] },
      ]),
    );
    renderTimeline();
    await waitFor(() => expect(screen.getByTestId("activation-event")).toBeInTheDocument());
    expect(screen.getAllByTestId("activation-event")).toHaveLength(1);
    expect(screen.getByText("displacement_reclaim, vwap_extension")).toBeInTheDocument();
  });
});

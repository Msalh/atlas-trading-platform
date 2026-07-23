import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RunCenterPage from "@/app/research-ops/run-center/page";

function readyStatusBody(overrides: Record<string, unknown> = {}) {
  return {
    database: { ok: true, reason: null, detail: "ok" },
    research_ledger: {
      status: "ready",
      reason: null,
      checks: {
        configuration_valid: { ok: true, reason: null, detail: null },
        ledger_directory: { ok: true, reason: null, detail: null },
        volume_mounted: { ok: true, reason: null, detail: null },
        jsonl_stores_initialized: { ok: true, reason: null, detail: null },
        registries_available: { ok: true, reason: null, detail: null },
      },
    },
    ...overrides,
  };
}

function snapshotBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    snapshot_id: "snap_1",
    created_at: "2026-07-23T14:00:00Z",
    ranking_policy_id: "v1",
    ranking_policy_version: "1.0",
    entries: [
      { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1" },
      { hypothesis_id: "h2", realization_id: null, rank: 2, score: 0.8, validation_id: null },
    ],
    ...overrides,
  };
}

function candidatesBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    snapshot_id: "snap_1",
    candidates: [
      { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1", prior_decisions: [] },
    ],
    ...overrides,
  };
}

function mockFetchByPath(responses: Record<string, { body: unknown; status?: number } | (() => never)>) {
  global.fetch = vi.fn(async (url: string | URL) => {
    const u = String(url);
    for (const [pathFragment, entry] of Object.entries(responses)) {
      if (u.includes(pathFragment)) {
        if (typeof entry === "function") entry();
        const { body, status = 200 } = entry as { body: unknown; status?: number };
        return new Response(JSON.stringify(body), { status });
      }
    }
    throw new Error(`unexpected fetch: ${u}`);
  }) as unknown as typeof fetch;
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RunCenterPage />
    </QueryClientProvider>,
  );
}

describe("RunCenterPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows a loading state for every summary card before any query resolves", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(4);
  });

  it("renders no NextStepLink - it is the last stop in the workflow order (Sprint 10 Slice G)", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.queryByText(/^Next: /)).not.toBeInTheDocument();
  });

  it("renders a healthy engine, all five cataloged operations, and no action buttons anywhere", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion/candidates": { body: candidatesBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Healthy")).toBeInTheDocument());
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getAllByText("snap_1").length).toBeGreaterThan(0);

    for (const name of ["Research Run", "Replay", "Benchmark", "Validation", "Promotion Review"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByText("Available")).toBeInTheDocument(); // Research Run
    expect(screen.getAllByText("Not Implemented")).toHaveLength(2); // Replay, Benchmark
    expect(screen.getAllByText("Not a Standalone Operation")).toHaveLength(2); // Validation, Promotion Review

    // 1 of 5 cataloged operations is currently available.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("of 5 cataloged")).toBeInTheDocument();

    expect(screen.getByText("1 of 2 entries in the latest snapshot carry a validation result.")).toBeInTheDocument();
    expect(screen.getByText("1 candidate currently awaiting review.")).toBeInTheDocument();

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows Degraded and marks Research Run Unavailable, with 0 available operations, when the Ledger is degraded", async () => {
    mockFetchByPath({
      status: {
        body: readyStatusBody({
          research_ledger: {
            status: "degraded",
            reason: "research_ledger_not_configured",
            checks: { configuration_valid: { ok: false, reason: "research_ledger_not_configured", detail: "RESEARCH_LEDGER_DIR is not set" } },
          },
        }),
      },
      "research/leaderboard": { body: { ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" }, status: 503 },
      "research/promotion/candidates": { body: { ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" }, status: 503 },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getAllByText("Degraded").length).toBeGreaterThan(0));
    // "research_ledger_not_configured" legitimately appears three times -
    // Engine Status, Ledger Readiness, and Research Run's own
    // availabilityDetail all derive from the same research_ledger.reason.
    expect(screen.getAllByText("research_ledger_not_configured").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("0")).toBeInTheDocument(); // Available Operations count
    // Research Run's own card shows "Unavailable", not "Degraded".
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("shows Backend Unreachable when the /status call itself fails", async () => {
    mockFetchByPath({
      status: () => {
        throw new Error("network down");
      },
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion/candidates": { body: candidatesBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Backend Unreachable")).toBeInTheDocument());
    expect(screen.getByText("Backend unreachable.")).toBeInTheDocument(); // Research Run's own detail
  });

  it("shows an empty state, not an error, when no snapshot has ever been recorded", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: { ok: false, error: "no leaderboard snapshots have been recorded yet" }, status: 404 },
      "research/promotion/candidates": { body: { ok: true, snapshot_id: null, candidates: [] } },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No snapshot recorded yet.")).toBeInTheDocument());
    expect(screen.getByText("No leaderboard snapshot has been recorded yet - this operation has not produced output.")).toBeInTheDocument();
  });

  it("never renders the API key or a raw stack trace anywhere on the page", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion/candidates": { body: candidatesBody() },
    });
    const { container } = renderWithClient();
    await waitFor(() => expect(screen.getByText("Healthy")).toBeInTheDocument());
    expect(container.textContent).not.toContain("ATLAS_API_KEY");
    expect(container.textContent).not.toContain("Bearer ");
  });
});

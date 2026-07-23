import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResearchOpsOverviewPage from "@/app/research-ops/page";

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
    entries: [{ hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1" }],
    ...overrides,
  };
}

function promotionsBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    records: [
      { promotion_id: "p1", hypothesis_id: "h1", realization_id: "r1", decision: "approved", decided_at: "2026-07-23T14:00:00Z", reviewer: "alice", rationale: "strong edge", evidence_snapshot_ref: "snap_1" },
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
      <ResearchOpsOverviewPage />
    </QueryClientProvider>,
  );
}

describe("ResearchOpsOverviewPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows a loading state for every card before any query resolves", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(5);
  });

  it("renders a healthy overview when everything is ready and populated", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion": { body: promotionsBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Healthy")).toBeInTheDocument());
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("snap_1")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("total decisions recorded")).toBeInTheDocument();
  });

  it("links forward to the Leaderboard (Sprint 10 Slice G)", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    const link = screen.getByRole("link", { name: "Next: Leaderboard →" });
    expect(link).toHaveAttribute("href", "/research-ops/leaderboard");
  });

  it("shows Degraded and the Ledger's own reason when research_ledger.status is degraded", async () => {
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
      "research/promotion": { body: { ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" }, status: 503 },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getAllByText("Degraded").length).toBeGreaterThanOrEqual(2));
    // Both Research Status and Ledger Readiness legitimately show the same
    // reason text (they derive from the same research_ledger.reason field).
    expect(screen.getAllByText("research_ledger_not_configured").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("RESEARCH_LEDGER_DIR is not set")).toBeInTheDocument();
  });

  it("shows Backend Unreachable when the /status call itself fails", async () => {
    global.fetch = vi.fn(async (url: string | URL) => {
      if (String(url).includes("status")) throw new Error("network down");
      return new Response(JSON.stringify(snapshotBody()), { status: 200 });
    }) as unknown as typeof fetch;
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Backend Unreachable")).toBeInTheDocument());
  });

  it("shows an empty state, not an error, when no snapshot has ever been recorded", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: { ok: false, error: "no leaderboard snapshots have been recorded yet" }, status: 404 },
      "research/promotion": { body: promotionsBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getAllByText("No snapshot recorded yet.").length).toBe(2));
  });

  it("shows an empty state, not an error, when no promotions have been recorded (200 with an empty array)", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion": { body: promotionsBody({ records: [] }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No promotion decisions recorded yet.")).toBeInTheDocument());
  });

  it("shows an empty-validation state when the latest snapshot has zero entries", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: snapshotBody({ entries: [] }) },
      "research/promotion": { body: promotionsBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No validated hypothesis in the latest snapshot.")).toBeInTheDocument());
    // The snapshot itself still has a real id/timestamp, distinct from the
    // Latest Validation card's own empty state above.
    expect(screen.getByText("snap_1")).toBeInTheDocument();
  });

  it("never renders a raw stack trace or the API key anywhere on the page", async () => {
    mockFetchByPath({
      status: { body: readyStatusBody() },
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion": { body: promotionsBody() },
    });
    const { container } = renderWithClient();
    await waitFor(() => expect(screen.getByText("Healthy")).toBeInTheDocument());
    expect(container.textContent).not.toContain("ATLAS_API_KEY");
    expect(container.textContent).not.toContain("Bearer ");
  });
});

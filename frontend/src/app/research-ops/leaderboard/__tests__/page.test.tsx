import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LeaderboardPage from "@/app/research-ops/leaderboard/page";

function snapshotBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    snapshot_id: "snap_1",
    created_at: "2026-07-23T14:00:00Z",
    ranking_policy_id: "v1",
    ranking_policy_version: "1.0",
    entries: [
      { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1" },
      { hypothesis_id: "h2", realization_id: null, rank: 2, score: 0.8, validation_id: "v2" },
    ],
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

function mockFetchByPath(responses: Record<string, { body: unknown; status?: number }>) {
  global.fetch = vi.fn(async (url: string | URL) => {
    const u = String(url);
    for (const [pathFragment, entry] of Object.entries(responses)) {
      if (u.includes(pathFragment)) {
        const { body, status = 200 } = entry;
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
      <LeaderboardPage />
    </QueryClientProvider>,
  );
}

describe("LeaderboardPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows a loading state for every summary card and the table area before any query resolves", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(5);
  });

  it("links forward to the Snapshot Explorer (Sprint 10 Slice G)", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    const link = screen.getByRole("link", { name: "Next: Snapshot Explorer →" });
    expect(link).toHaveAttribute("href", "/research-ops/snapshot");
  });

  it("renders the summary strip and table rows, including derived promotion status, once data resolves", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion": { body: promotionsBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("snap_1")).toBeInTheDocument());
    // "2" legitimately appears twice - the Total Ranked Hypotheses stat and
    // row 2's own Rank cell - both are correct, not a collision to avoid.
    expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("h1")).toBeInTheDocument();
    expect(screen.getByText("h2")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument(); // h1/r1 has a matching promotion record
    expect(screen.getByText("Pending Review")).toBeInTheDocument(); // h2 has none
  });

  it("shows an empty state, not an error, when no snapshot has ever been recorded", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: { ok: false, error: "no leaderboard snapshots have been recorded yet" }, status: 404 },
      "research/promotion": { body: promotionsBody({ records: [] }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No snapshot has been recorded yet.")).toBeInTheDocument());
  });

  it("shows an empty state when the latest snapshot has zero entries", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody({ entries: [] }) },
      "research/promotion": { body: promotionsBody({ records: [] }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("The latest snapshot has no ranked hypotheses.")).toBeInTheDocument());
  });

  it("shows a degraded-ledger error, not a generic error, when the leaderboard call fails with 503", async () => {
    mockFetchByPath({
      "research/leaderboard": {
        body: { ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" },
        status: 503,
      },
      "research/promotion": {
        body: { ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" },
        status: 503,
      },
    });
    renderWithClient();

    await waitFor(() =>
      expect(screen.getAllByText("research ledger storage is degraded: research_ledger_not_configured").length).toBeGreaterThan(0),
    );
  });

  it("never renders the API key or a raw stack trace anywhere on the page", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/promotion": { body: promotionsBody() },
    });
    const { container } = renderWithClient();
    await waitFor(() => expect(screen.getByText("snap_1")).toBeInTheDocument());
    expect(container.textContent).not.toContain("ATLAS_API_KEY");
    expect(container.textContent).not.toContain("Bearer ");
  });
});

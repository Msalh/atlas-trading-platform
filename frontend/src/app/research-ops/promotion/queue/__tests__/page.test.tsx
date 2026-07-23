import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PromotionQueuePage from "@/app/research-ops/promotion/queue/page";

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

function candidatesBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    snapshot_id: "snap_1",
    candidates: [
      { hypothesis_id: "h1", realization_id: "r1", rank: 1, score: 1.0, validation_id: "v1", prior_decisions: [] },
      {
        hypothesis_id: "h2",
        realization_id: "r2",
        rank: 2,
        score: 0.8,
        validation_id: "v2",
        prior_decisions: [
          { promotion_id: "p1", hypothesis_id: "h2", realization_id: "r2", decision: "deferred", decided_at: "2026-07-23T13:00:00Z", reviewer: "alice", rationale: "needs more data", evidence_snapshot_ref: "snap_0" },
        ],
      },
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
      <PromotionQueuePage />
    </QueryClientProvider>,
  );
}

describe("PromotionQueuePage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows a loading state for every summary card and the table area before any query resolves", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(4);
  });

  it("links forward to the Promotion History (Sprint 10 Slice G)", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    const link = screen.getByRole("link", { name: "Next: Promotion History →" });
    expect(link).toHaveAttribute("href", "/research-ops/promotion/history");
  });

  it("renders the summary strip and queue rows, including a fresh pending candidate and one being reconsidered", async () => {
    mockFetchByPath({
      "research/promotion/candidates": { body: candidatesBody() },
      "research/leaderboard": { body: snapshotBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getAllByText("snap_1").length).toBeGreaterThan(0));
    expect(screen.getByText("2")).toBeInTheDocument(); // Awaiting Review count
    expect(screen.getByText("h1")).toBeInTheDocument();
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
    expect(screen.getByText("h2")).toBeInTheDocument();
    expect(screen.getByText("Deferred")).toBeInTheDocument();
  });

  it("shows the snapshot's created_at once candidatesQuery and snapshotQuery resolve to the same snapshot_id", async () => {
    mockFetchByPath({
      "research/promotion/candidates": { body: candidatesBody({ snapshot_id: "snap_1" }) },
      "research/leaderboard": { body: snapshotBody({ snapshot_id: "snap_1", created_at: "2026-07-23T14:00:00Z" }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Jul 23, 09:00:00 AM CT")).toBeInTheDocument());
  });

  it("shows Unavailable, not a mismatched timestamp, when candidatesQuery and snapshotQuery resolve to different snapshot_ids", async () => {
    mockFetchByPath({
      "research/promotion/candidates": { body: candidatesBody({ snapshot_id: "snap_1" }) },
      "research/leaderboard": { body: snapshotBody({ snapshot_id: "snap_2", created_at: "2026-07-23T15:00:00Z" }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("h1")).toBeInTheDocument());
    expect(screen.getByText("Unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/09:00:00 AM CT|10:00:00 AM CT/)).not.toBeInTheDocument();
  });

  it("renders a declined candidate as Previously Declined, not Declined - it remains eligible for reconsideration", async () => {
    mockFetchByPath({
      "research/promotion/candidates": {
        body: candidatesBody({
          candidates: [
            {
              hypothesis_id: "h3",
              realization_id: "r3",
              rank: 1,
              score: 0.7,
              validation_id: "v3",
              prior_decisions: [
                { promotion_id: "p2", hypothesis_id: "h3", realization_id: "r3", decision: "declined", decided_at: "2026-07-23T12:00:00Z", reviewer: "bob", rationale: "insufficient sample size", evidence_snapshot_ref: "snap_0" },
              ],
            },
          ],
        }),
      },
      "research/leaderboard": { body: snapshotBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Previously Declined")).toBeInTheDocument());
    expect(screen.queryByText("Declined")).not.toBeInTheDocument();
  });

  it("has no per-row Timestamp column", async () => {
    mockFetchByPath({
      "research/promotion/candidates": { body: candidatesBody() },
      "research/leaderboard": { body: snapshotBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("h1")).toBeInTheDocument());
    expect(screen.queryByText("Timestamp")).not.toBeInTheDocument();
  });

  it("shows an empty state, not an error, when no snapshot has ever been recorded", async () => {
    mockFetchByPath({
      "research/promotion/candidates": { body: { ok: true, snapshot_id: null, candidates: [] } },
      "research/leaderboard": { body: { ok: false, error: "no leaderboard snapshots have been recorded yet" }, status: 404 },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No snapshot has been recorded yet.")).toBeInTheDocument());
  });

  it("shows an empty state when the snapshot exists but nothing is awaiting review", async () => {
    mockFetchByPath({
      "research/promotion/candidates": { body: candidatesBody({ candidates: [] }) },
      "research/leaderboard": { body: snapshotBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No candidates are currently awaiting review.")).toBeInTheDocument());
  });

  it("shows a degraded-ledger error, not a generic error, when the candidates call fails with 503", async () => {
    mockFetchByPath({
      "research/promotion/candidates": {
        body: { ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" },
        status: 503,
      },
      "research/leaderboard": {
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
      "research/promotion/candidates": { body: candidatesBody() },
      "research/leaderboard": { body: snapshotBody() },
    });
    const { container } = renderWithClient();
    await waitFor(() => expect(screen.getAllByText("snap_1").length).toBeGreaterThan(0));
    expect(container.textContent).not.toContain("ATLAS_API_KEY");
    expect(container.textContent).not.toContain("Bearer ");
  });
});

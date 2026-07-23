import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SnapshotExplorerPage from "@/app/research-ops/snapshot/page";

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

function lineageBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    hypothesis_id: "h1",
    realization_id: "r1",
    promotion_records: [
      { promotion_id: "p1", hypothesis_id: "h1", realization_id: "r1", decision: "approved", reviewer: "alice", rationale: "looks good", decided_at: "2026-07-23T15:00:00Z" },
    ],
    validation_results: [
      { validation_id: "v1", hypothesis_id: "h1", verdict: "supported", justification: "ok", validated_at: "2026-07-23T14:30:00Z", out_of_sample: true },
    ],
    evidence: [{ evidence_id: "e1", experiment_id: "exp1", computed_at: "2026-07-23T14:20:00Z", metrics: { sharpe: 1.2 } }],
    experiments: [{ experiment_id: "exp1", hypothesis_id: "h1", executed_at: "2026-07-23T14:10:00Z", code_version: "abc123", passed: true }],
    realization: { realization_id: "r1", hypothesis_id: "h1", kind: "parameter_grid", version: "1", parameters: {}, status: "active", created_at: "2026-07-23T14:00:00Z" },
    warnings: [],
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
      <SnapshotExplorerPage />
    </QueryClientProvider>,
  );
}

describe("SnapshotExplorerPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows a loading state before the snapshot query resolves", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(3);
  });

  it("links forward to the Promotion Queue (Sprint 10 Slice G)", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    const link = screen.getByRole("link", { name: "Next: Promotion Queue →" });
    expect(link).toHaveAttribute("href", "/research-ops/promotion/queue");
  });

  it("renders the snapshot summary and defaults the entry selector to the first (rank 1) entry", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/lineage": { body: lineageBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("snap_1")).toBeInTheDocument());
    expect(screen.getByText("2")).toBeInTheDocument(); // Entry Count
    expect(screen.getByRole("combobox")).toHaveValue("0");
  });

  it("renders the complete lineage chain for the selected entry", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/lineage": { body: lineageBody() },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Hypothesis")).toBeInTheDocument());
    expect(screen.getByText("Realization")).toBeInTheDocument();
    expect(screen.getByText("Experiment")).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("Validation")).toBeInTheDocument();
    expect(screen.getByText("Promotion")).toBeInTheDocument();
    expect(screen.getByText("exp1")).toBeInTheDocument();
    expect(screen.getByText("Supported")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("shows a dedicated message, not a lineage query, for an entry with no validation_id", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody({ entries: [{ hypothesis_id: "h2", realization_id: null, rank: 1, score: 0.8, validation_id: null }] }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("This entry has no recorded validation - lineage is unavailable.")).toBeInTheDocument());
  });

  it("shows an empty state, not an error, when no snapshot has ever been recorded", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: { ok: false, error: "no leaderboard snapshots have been recorded yet" }, status: 404 },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No snapshot has been recorded yet.")).toBeInTheDocument());
  });

  it("shows an empty state when the latest snapshot has zero entries", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody({ entries: [] }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("The latest snapshot has no ranked hypotheses.")).toBeInTheDocument());
  });

  it("shows a degraded-ledger error when the snapshot call fails with 503", async () => {
    mockFetchByPath({
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

  it("shows an empty state, not a crash, when the lineage lookup itself 404s", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/lineage": { body: { ok: false, error: "no validation result with id 'v1'" }, status: 404 },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No lineage could be found for this entry's validation result.")).toBeInTheDocument());
  });

  it("surfaces lineage warnings without hiding the rest of the chain", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/lineage": { body: lineageBody({ warnings: ["evidence 'e2' referenced but not found in the Ledger"] }) },
    });
    renderWithClient();

    await waitFor(() => expect(screen.getByText("evidence 'e2' referenced but not found in the Ledger")).toBeInTheDocument());
    expect(screen.getByText("Hypothesis")).toBeInTheDocument();
  });

  it("never renders the API key or a raw stack trace anywhere on the page", async () => {
    mockFetchByPath({
      "research/leaderboard": { body: snapshotBody() },
      "research/lineage": { body: lineageBody() },
    });
    const { container } = renderWithClient();
    await waitFor(() => expect(screen.getByText("snap_1")).toBeInTheDocument());
    expect(container.textContent).not.toContain("ATLAS_API_KEY");
    expect(container.textContent).not.toContain("Bearer ");
  });
});

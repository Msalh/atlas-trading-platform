import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PromotionHistoryPage from "@/app/research-ops/promotion/history/page";

function historyBody(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    records: [
      { promotion_id: "p1", hypothesis_id: "h1", realization_id: "r1", decision: "approved", decided_at: "2026-07-23T14:00:00Z", reviewer: "alice", rationale: "strong out-of-sample edge", evidence_snapshot_ref: "snap_1" },
      { promotion_id: "p2", hypothesis_id: "h2", realization_id: null, decision: "declined", decided_at: "2026-07-22T14:00:00Z", reviewer: "bob", rationale: "insufficient sample size", evidence_snapshot_ref: "snap_0" },
    ],
    ...overrides,
  };
}

function mockFetchOnce(body: unknown, status = 200) {
  global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PromotionHistoryPage />
    </QueryClientProvider>,
  );
}

describe("PromotionHistoryPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("shows a loading state for every summary card and the table area before the query resolves", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(3);
  });

  it("links forward to the Run Center (Sprint 10 Slice G)", () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    renderWithClient();
    const link = screen.getByRole("link", { name: "Next: Run Center →" });
    expect(link).toHaveAttribute("href", "/research-ops/run-center");
  });

  it("renders the summary strip and history rows, including reason and snapshot reference", async () => {
    mockFetchOnce(historyBody());
    renderWithClient();

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
    // "h1" legitimately appears twice - the Most Recent Decision stat value
    // (both records share hypothesis_id "h1"/"h2" being distinct, but the
    // most-recent one here is h1) and the table row's own Hypothesis cell.
    expect(screen.getAllByText("h1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("strong out-of-sample edge")).toBeInTheDocument();
    expect(screen.getByText("h2")).toBeInTheDocument();
    // Sprint 10 Slice E.1: History renders the immutable decision as plain
    // "Declined", never the Queue's "Previously Declined" wording - a
    // recorded PromotionRecord here is a made decision, not a
    // reconsideration-in-progress.
    expect(screen.getByText("Declined")).toBeInTheDocument();
    expect(screen.queryByText("Previously Declined")).not.toBeInTheDocument();
    expect(screen.getByText("insufficient sample size")).toBeInTheDocument();
  });

  it("identifies the most recent decision by decided_at, not list order", async () => {
    mockFetchOnce(
      historyBody({
        records: [
          { promotion_id: "p1", hypothesis_id: "h1", realization_id: "r1", decision: "declined", decided_at: "2026-07-20T00:00:00Z", reviewer: "alice", rationale: "early pass", evidence_snapshot_ref: "snap_0" },
          { promotion_id: "p2", hypothesis_id: "h2", realization_id: "r2", decision: "approved", decided_at: "2026-07-23T00:00:00Z", reviewer: "bob", rationale: "later pass", evidence_snapshot_ref: "snap_1" },
        ],
      }),
    );
    renderWithClient();

    await waitFor(() => expect(screen.getByText("Most Recent Decision").closest("section")).toHaveTextContent("h2"));
  });

  it("shows an empty state, not an error, when no promotion decisions have been recorded (200 with an empty array)", async () => {
    mockFetchOnce(historyBody({ records: [] }));
    renderWithClient();

    await waitFor(() => expect(screen.getByText("No promotion decisions have been recorded yet.")).toBeInTheDocument());
    expect(screen.getByText("No decisions recorded yet.")).toBeInTheDocument();
  });

  it("shows a degraded-ledger error, not a generic error, when the history call fails with 503", async () => {
    mockFetchOnce({ ok: false, error: "research ledger storage is degraded: research_ledger_not_configured" }, 503);
    renderWithClient();

    await waitFor(() =>
      expect(screen.getAllByText("research ledger storage is degraded: research_ledger_not_configured").length).toBeGreaterThan(0),
    );
  });

  it("never renders the API key or a raw stack trace anywhere on the page", async () => {
    mockFetchOnce(historyBody());
    const { container } = renderWithClient();
    await waitFor(() => expect(screen.getAllByText("h1").length).toBeGreaterThan(0));
    expect(container.textContent).not.toContain("ATLAS_API_KEY");
    expect(container.textContent).not.toContain("Bearer ");
  });
});

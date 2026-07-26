import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MarketViewPage from "@/app/market-view/page";
import { traderNowFixture } from "@/test/traderNowFixture";

function renderPage() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MarketViewPage />
  </QueryClientProvider>);
}

describe("unified TraderNow Market View", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders every authority section and keeps candidate non-recommendational", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(traderNowFixture()), { status: 200 }));
    renderPage();
    await screen.findByRole("heading", { name: "Market" });
    for (const heading of ["Market", "Trust and availability", "Facts", "Setups", "Context",
      "Interpretation", "Strategy", "Risk", "Decision"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    const strategy = screen.getByRole("heading", { name: "Strategy" }).closest("section")!;
    expect(within(strategy).getAllByText("candidate").length).toBeGreaterThan(0);
    expect(within(strategy).getByText(/never an entry recommendation/i)).toBeInTheDocument();
    expect(screen.queryByText("ENTRY CONDITIONS MET")).not.toBeInTheDocument();
  });

  it("shows absent Risk honestly and preserves decision.not_implemented", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(traderNowFixture()), { status: 200 }));
    renderPage();
    expect(await screen.findByText(/Risk was not supplied/)).toBeInTheDocument();
    expect(screen.getByText(/No risk state has been inferred/)).toBeInTheDocument();
    expect(screen.getByText(/Decision Engine not implemented/)).toBeInTheDocument();
    expect(screen.getByText(/No Decision Engine state exists/)).toBeInTheDocument();
  });

  it("renders stale and partially unavailable sections without substitution", async () => {
    const body = traderNowFixture({
      source_trust: { ...traderNowFixture().source_trust!, freshness: {
        ...traderNowFixture().source_trust!.freshness, status: "stale", lateness_seconds: 600,
      } },
      context: { availability: { status: "unavailable", reason_codes: ["context_unavailable"] }, data: null },
      interpretations: { availability: { status: "unavailable", reason_codes: [] }, interpretations: [] },
      strategy: { availability: { status: "unavailable", reason_codes: [] }, decisions: [] },
    });
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));
    renderPage();
    expect(await screen.findByText(/Market data is stale/)).toBeInTheDocument();
    expect(screen.getByText("Market Context is unavailable.")).toBeInTheDocument();
    expect(screen.getByText("No Strategy decision is available.")).toBeInTheDocument();
  });

  it.each([
    [401, "TraderNow authentication failed"],
    [502, "TraderNow is currently unavailable"],
  ])("renders sanitized HTTP %s state", async (status, message) => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: false, error: "safe" }), { status }));
    renderPage();
    expect(await screen.findByText(new RegExp(message))).toBeInTheDocument();
  });

  it("fails closed on malformed success", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ schema_version: "trader_now_response.v2" }), { status: 200 }));
    renderPage();
    expect(await screen.findByText(/malformed response/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Strategy" })).not.toBeInTheDocument();
  });

  it("renders a loading state", () => {
    vi.spyOn(global, "fetch").mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading live TraderNow analysis");
  });
});

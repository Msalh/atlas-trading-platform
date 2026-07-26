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
    expect(screen.queryByText(/\bENTER\b.*recommendation/i)).not.toBeInTheDocument();
  });

  it("shows absent Risk honestly and preserves decision.not_implemented", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(traderNowFixture()), { status: 200 }));
    renderPage();
    expect(await screen.findByText(/Risk was not supplied/)).toBeInTheDocument();
    expect(screen.getByText(/No risk state has been inferred/)).toBeInTheDocument();
    expect(screen.getAllByText(/Decision Engine not implemented/)).toHaveLength(2);
    expect(screen.getByText(/No Decision Engine state exists/)).toBeInTheDocument();
    const summary = screen.getByRole("heading", { name: "Operational summary" }).closest("section")!;
    expect(within(summary).getByText(/Risk is absent; no risk state has been inferred/i)).toBeInTheDocument();
    expect(within(summary).getByText(/Decision Engine not implemented/i)).toBeInTheDocument();
    expect(within(summary).getByText(/No WAIT, PREPARE, ENTER/i)).toBeInTheDocument();
  });

  it("presents only canonical response identities and does not imply a listed contract", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(traderNowFixture()), { status: 200 }));
    renderPage();
    expect(await screen.findByText(/Economic product MNQ · Source series tradingview:MNQ1! · 5m/i)).toBeInTheDocument();
    const market = screen.getByRole("heading", { name: "Market" }).closest("section")!;
    expect(within(market).getByText("MNQ")).toBeInTheDocument();
    expect(within(market).getByText("tradingview:MNQ1!")).toBeInTheDocument();
    expect(within(market).getByText("Unresolved")).toBeInTheDocument();
    expect(screen.queryByText(/MNQU6|ICT_Funded_v1/)).not.toBeInTheDocument();
  });

  it("contains long canonical Strategy identifiers on narrow layouts", async () => {
    const fixture = traderNowFixture();
    const longStrategyId = "deterministic_strategy_identifier_that_must_wrap_without_expanding_the_page";
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(traderNowFixture({
      strategy: {
        ...fixture.strategy,
        decisions: fixture.strategy.decisions.map((decision) => ({ ...decision, strategy_id: longStrategyId })),
      },
    })), { status: 200 }));
    renderPage();
    const identifier = await screen.findByText(`${longStrategyId}@strategy.v1`);
    expect(identifier).toHaveClass("min-w-0", "break-all");
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
    expect(screen.getAllByText("No Strategy decision is available.")).toHaveLength(2);
  });

  it.each([
    [401, "Authentication required", "TraderNow authentication failed"],
    [403, "Access denied", "not authorized"],
    [502, "Live analysis unavailable", "TraderNow is currently unavailable"],
  ])("renders sanitized HTTP %s state", async (status, title, detail) => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: false, error: "safe" }), { status }));
    renderPage();
    expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.getByText(new RegExp(detail))).toBeInTheDocument();
  });

  it("fails closed on malformed success", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ schema_version: "trader_now_response.v2" }), { status: 200 }));
    renderPage();
    expect(await screen.findByRole("heading", { name: "Invalid analysis response" })).toBeInTheDocument();
    expect(screen.getByText(/malformed or contract-invalid response/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Strategy" })).not.toBeInTheDocument();
  });

  it("renders a loading state", () => {
    vi.spyOn(global, "fetch").mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading live TraderNow analysis");
  });
});

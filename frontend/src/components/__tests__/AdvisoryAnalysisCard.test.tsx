import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdvisoryAnalysisCard } from "@/components/AdvisoryAnalysisCard";

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AdvisoryAnalysisCard />
    </QueryClientProvider>,
  );
}

function trustedResponse() {
  return {
    schema_version: "trader_now_response.v2",
    input_snapshot_at: "2026-08-06T12:00:00Z",
    identity: { product: "MNQ", symbol: "MNQ", timeframe: "5m" },
    trust: { status: "trusted" },
    source_trust: {
      overall: "trusted",
      structural_validity: "valid",
      freshness: { status: "current", latest_closed_at: "2026-08-06T12:00:00Z" },
    },
    market: {
      latest_closed_at: "2026-08-06T12:00:00Z",
      latest_bar: { occurred_at: "2026-08-06T12:00:00Z", close: { value: 21234.25 } },
    },
    context: { data: { session: { phase: "rth" }, volatility: { regime: "expanded" } } },
    strategy: {
      availability: { status: "available" },
      decisions: [{
        disposition: "candidate",
        direction: "short",
        stop: { value: 21250 },
        target: { value: 21200 },
        confidence: 0.76,
        setup_ids: ["reversal"],
      }],
    },
  };
}

describe("AdvisoryAnalysisCard", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("does not fetch until the user requests analysis, then renders the approved projection", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify(trustedResponse()), { status: 200 })) as typeof fetch;
    renderCard();

    expect(global.fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));

    await waitFor(() => expect(screen.getByText("Sell")).toBeInTheDocument());
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(String(vi.mocked(global.fetch).mock.calls[0][0])).toContain(
      "symbol=MNQ&timeframe=5m&strategy_id=displacement_volume_context",
    );
    expect(screen.getByText("21,234.25")).toBeInTheDocument();
    expect(screen.getByText("Entry (confirmation close)")).toBeInTheDocument();
    expect(screen.queryByText("Short candidate")).not.toBeInTheDocument();
    expect(screen.getByText(/Advisory \/ paper-only/)).toBeInTheDocument();
  });

  it("renders a safe failure without advisory values", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify({ detail: "unavailable" }), { status: 503 })) as typeof fetch;
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText(/No advisory values were produced/)).toBeInTheDocument());
    expect(screen.queryByText("Buy")).not.toBeInTheDocument();
    expect(screen.queryByText("Sell")).not.toBeInTheDocument();
    expect(screen.getByText(/Advisory \/ paper-only/)).toBeInTheDocument();
  });

  it.each([
    ["long", "Buy"],
    ["short", "Sell"],
  ])("maps the internal %s candidate to the user-facing %s action", async (direction, label) => {
    const body = trustedResponse();
    body.strategy.decisions[0].direction = direction;
    global.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })) as typeof fetch;
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
  });

  it("maps no candidate to No Trade and keeps Unavailable separate", async () => {
    const noTrade = trustedResponse();
    noTrade.strategy.decisions = [];
    global.fetch = vi.fn(async () => new Response(JSON.stringify(noTrade), { status: 200 })) as typeof fetch;
    const first = renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText("No Trade")).toBeInTheDocument());
    expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();
    first.unmount();

    const unavailable = trustedResponse();
    unavailable.source_trust.freshness.status = "stale";
    global.fetch = vi.fn(async () => new Response(JSON.stringify(unavailable), { status: 200 })) as typeof fetch;
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText("Unavailable")).toBeInTheDocument());
    expect(screen.queryByText("No Trade")).not.toBeInTheDocument();
  });
});

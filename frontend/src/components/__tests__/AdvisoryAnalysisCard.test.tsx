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

function manualResponse(aiAvailable = false) {
  return {
    schema_version: "manual_advisory_response.v1",
    trader_now: trustedResponse(),
    ai_explanation: aiAvailable ? {
      status: "available", summary: "The verified strategy state contains a short candidate.",
      claims: [{ claim_id: "claim-1", kind: "explanation", text: "The candidate is grounded in the supplied strategy evidence.", citations: ["/evidence/strategy/decisions/0/disposition"] }],
      limitations: ["advisory_only", "single_snapshot_only"], reason: null,
    } : {
      status: "unavailable", summary: null, claims: [], limitations: [], reason: "analysis_unavailable",
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
    global.fetch = vi.fn(async () => new Response(JSON.stringify(manualResponse(true)), { status: 200 })) as typeof fetch;
    renderCard();

    expect(global.fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));

    await waitFor(() => expect(screen.getByText("Sell")).toBeInTheDocument());
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(String(vi.mocked(global.fetch).mock.calls[0][0])).toBe("/api/proxy/trader-now/manual-advisory");
    expect(vi.mocked(global.fetch).mock.calls[0][1]).toMatchObject({ method: "POST" });
    expect(screen.getByText("21,234.25")).toBeInTheDocument();
    expect(screen.getByText("21,250")).toBeInTheDocument();
    expect(screen.getByText("21,200")).toBeInTheDocument();
    expect(screen.getByText("Entry (confirmation close)")).toBeInTheDocument();
    expect(screen.queryByText("Short candidate")).not.toBeInTheDocument();
    expect(screen.getByText(/Advisory \/ paper-only/)).toBeInTheDocument();
    expect(screen.getByText("AI-assisted explanation")).toBeInTheDocument();
    expect(screen.getByText(/Evidence: \/evidence\/strategy\/decisions\/0\/disposition/)).toBeInTheDocument();
  });

  it("does not start a concurrent request when the pending button is clicked again", async () => {
    let resolveResponse!: (response: Response) => void;
    global.fetch = vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve; })) as typeof fetch;
    renderCard();

    const button = screen.getByRole("button", { name: "Analyze latest state" });
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyzing…" })).toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Analyzing…" }));
    expect(global.fetch).toHaveBeenCalledTimes(1);

    resolveResponse(new Response(JSON.stringify(manualResponse()), { status: 200 }));
    await waitFor(() => expect(screen.getByText("Sell")).toBeInTheDocument());
    expect(global.fetch).toHaveBeenCalledTimes(1);
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
    const envelope = manualResponse();
    envelope.trader_now = body;
    global.fetch = vi.fn(async () => new Response(JSON.stringify(envelope), { status: 200 })) as typeof fetch;
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
  });

  it("maps no candidate to No Trade and keeps Unavailable separate", async () => {
    const noTrade = trustedResponse();
    noTrade.strategy.decisions = [];
    const noTradeEnvelope = manualResponse();
    noTradeEnvelope.trader_now = noTrade;
    global.fetch = vi.fn(async () => new Response(JSON.stringify(noTradeEnvelope), { status: 200 })) as typeof fetch;
    const first = renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText("No Trade")).toBeInTheDocument());
    expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();
    first.unmount();

    const unavailable = trustedResponse();
    unavailable.source_trust.freshness.status = "stale";
    const unavailableEnvelope = manualResponse();
    unavailableEnvelope.trader_now = unavailable;
    global.fetch = vi.fn(async () => new Response(JSON.stringify(unavailableEnvelope), { status: 200 })) as typeof fetch;
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText("Unavailable")).toBeInTheDocument());
    expect(screen.queryByText("No Trade")).not.toBeInTheDocument();
  });

  it("keeps deterministic values when the optional AI explanation is unavailable", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify(manualResponse()), { status: 200 })) as typeof fetch;
    renderCard();
    fireEvent.click(screen.getByRole("button", { name: "Analyze latest state" }));
    await waitFor(() => expect(screen.getByText("Sell")).toBeInTheDocument());
    expect(screen.getByText("Deterministic advisory")).toBeInTheDocument();
    expect(screen.getByText(/AI explanation is unavailable/)).toBeInTheDocument();
    expect(screen.getByText("21,234.25")).toBeInTheDocument();
  });
});

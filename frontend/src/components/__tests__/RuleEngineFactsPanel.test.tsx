import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RuleEngineFactsPanel } from "@/components/RuleEngineFactsPanel";
import { LiveSelectorProvider } from "@/lib/liveSelector";

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LiveSelectorProvider>
        <RuleEngineFactsPanel />
      </LiveSelectorProvider>
    </QueryClientProvider>,
  );
}

describe("RuleEngineFactsPanel", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders a computed boolean fact as Yes/No and an insufficient_data fact neutrally", async () => {
    global.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ok: true,
            found: true,
            data: {
              schema_version: "1.0",
              symbol: "MNQU6",
              timeframe: "5m",
              occurred_at: "2026-07-20T11:55:00Z",
              facts: [
                { name: "displacement", status: "computed", value: true, definition_version: "1.0", evidence: {} },
                { name: "reclaim", status: "insufficient_data", definition_version: "1.0", reason: "not enough history" },
              ],
            },
          }),
          { status: 200 },
        ),
    ) as unknown as typeof fetch;

    renderPanel();
    await waitFor(() => expect(screen.getByText("displacement")).toBeInTheDocument());
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("reclaim")).toBeInTheDocument();
    expect(screen.getByText("insufficient data")).toBeInTheDocument();
  });

  it("shows a neutral not-ingested message when found=false", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true, found: false, data: null }), { status: 200 })) as unknown as typeof fetch;
    renderPanel();
    await waitFor(() => expect(screen.getByText(/No MarketState has been ingested yet/)).toBeInTheDocument());
  });
});

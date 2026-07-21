import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MarketViewPage from "@/app/market-view/page";
import { LiveSelectorProvider } from "@/lib/liveSelector";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LiveSelectorProvider>
        <MarketViewPage />
      </LiveSelectorProvider>
    </QueryClientProvider>,
  );
}

function setupEngineBody() {
  return {
    ok: true,
    found: true,
    envelope: {
      schema_version: "1.0",
      source_track: "live",
      symbol: "MNQU6",
      timeframe: "5m",
      generated_at: "2026-07-20T12:00:00Z",
      data_as_of: "2026-07-20T11:55:00Z",
      code_version: "abc123",
      warnings: [],
    },
    data: {
      schema_version: "1.0",
      symbol: "MNQU6",
      timeframe: "5m",
      occurred_at: "2026-07-20T11:55:00Z",
      setups: [],
    },
  };
}

function ruleEngineBody() {
  return {
    ok: true,
    found: true,
    data: {
      schema_version: "1.0",
      symbol: "MNQU6",
      timeframe: "5m",
      occurred_at: "2026-07-20T11:55:00Z",
      facts: [],
    },
  };
}

describe("MarketViewPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders both panels and a LIVE freshness badge sourced from setup-engine's envelope", async () => {
    let setupEngineCalls = 0;
    global.fetch = vi.fn(async (url: string | URL) => {
      const u = String(url);
      if (u.includes("setup-engine/latest")) {
        setupEngineCalls += 1;
        return new Response(JSON.stringify(setupEngineBody()), { status: 200 });
      }
      if (u.includes("rule-engine/latest")) {
        return new Response(JSON.stringify(ruleEngineBody()), { status: 200 });
      }
      throw new Error(`unexpected URL ${u}`);
    }) as unknown as typeof fetch;

    renderPage();

    await waitFor(() => expect(screen.getByText("Rule Engine Facts")).toBeInTheDocument());
    expect(screen.getByText("Setup Engine")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/LIVE/)).toBeInTheDocument());

    // The page's own useQuery and SetupEngineViewer's internal useQuery share
    // the exact same query key - react-query must dedupe them into one
    // network request, not two (architecture §9's shared-fetch discipline,
    // applied here one page early).
    await waitFor(() => expect(setupEngineCalls).toBe(1));
  });
});

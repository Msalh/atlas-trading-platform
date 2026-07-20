import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SetupEngineViewer } from "@/components/SetupEngineViewer";
import { LiveSelectorProvider } from "@/lib/liveSelector";

function renderViewer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LiveSelectorProvider>
        <SetupEngineViewer />
      </LiveSelectorProvider>
    </QueryClientProvider>,
  );
}

const envelope = {
  schema_version: "1.0",
  source_track: "live",
  symbol: "MNQU6",
  timeframe: "5m",
  generated_at: "2026-07-20T12:00:00Z",
  data_as_of: "2026-07-20T11:55:00Z",
  code_version: "abc123",
  warnings: [] as string[],
};

describe("SetupEngineViewer", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders a detected setup as 'Active' with no signal/recommendation language", async () => {
    global.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ok: true,
            found: true,
            envelope,
            data: {
              schema_version: "1.0",
              symbol: "MNQU6",
              timeframe: "5m",
              occurred_at: "2026-07-20T11:55:00Z",
              setups: [
                {
                  name: "displacement_reclaim",
                  status: "computed",
                  detected: true,
                  severity: "strong",
                  definition_version: "1.0",
                  evidence: { supporting_facts: [] },
                },
              ],
            },
          }),
          { status: 200 },
        ),
    ) as unknown as typeof fetch;

    renderViewer();
    await waitFor(() => expect(screen.getByText("displacement_reclaim")).toBeInTheDocument());
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText(/evidence strength: strong/)).toBeInTheDocument();

    const bannedWords = ["signal", "bullish", "bearish", "buy", "sell", "recommend"];
    const bodyText = document.body.textContent?.toLowerCase() ?? "";
    for (const word of bannedWords) {
      expect(bodyText).not.toContain(word);
    }
  });

  it("renders a non-detected computed setup as 'Not active' without severity", async () => {
    global.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ok: true,
            found: true,
            envelope,
            data: {
              schema_version: "1.0",
              symbol: "MNQU6",
              timeframe: "5m",
              occurred_at: "2026-07-20T11:55:00Z",
              setups: [
                {
                  name: "liquidity_sweep_reversal",
                  status: "computed",
                  detected: false,
                  severity: null,
                  definition_version: "1.0",
                  evidence: { supporting_facts: [] },
                },
              ],
            },
          }),
          { status: 200 },
        ),
    ) as unknown as typeof fetch;

    renderViewer();
    await waitFor(() => expect(screen.getByText("Not active")).toBeInTheDocument());
    expect(screen.queryByText(/evidence strength/)).not.toBeInTheDocument();
  });

  it("shows a neutral not-ingested message when found=false", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true, found: false, data: null }), { status: 200 })) as unknown as typeof fetch;
    renderViewer();
    await waitFor(() => expect(screen.getByText(/No MarketState has been ingested yet/)).toBeInTheDocument());
  });
});

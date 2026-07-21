import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActiveSetupBundle } from "@/components/ActiveSetupBundle";
import { Timeline } from "@/components/Timeline";
import { LiveSelectorProvider } from "@/lib/liveSelector";

// F4t / requirement 9: Active Setup Bundle, Timeline, and (later) Episode
// Inspector must produce exactly one request per polling tick when mounted
// together, not one per consumer - this is what useLiveEpisodes's shared
// query key exists to guarantee.
describe("useLiveEpisodes shared fetch across consumers", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("issues exactly one /setup-engine/episodes/live request when ActiveSetupBundle and Timeline mount together", async () => {
    let callCount = 0;
    global.fetch = vi.fn(async () => {
      callCount += 1;
      return new Response(
        JSON.stringify({
          ok: true,
          found: true,
          envelope: {
            schema_version: "1.0",
            source_track: "live",
            symbol: "MNQU6",
            timeframe: "5m",
            generated_at: "t",
            data_as_of: "t",
            code_version: "abc",
            warnings: [],
          },
          window: { requested: 500, actually_used: 500 },
          setups: {},
          segments: [],
          activation_events: [],
        }),
        { status: 200 },
      );
    }) as unknown as typeof fetch;

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <LiveSelectorProvider>
          <ActiveSetupBundle />
          <Timeline />
        </LiveSelectorProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText("No setups are currently active.")).toBeInTheDocument());
    expect(callCount).toBe(1);
  });
});

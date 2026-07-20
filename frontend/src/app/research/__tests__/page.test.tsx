import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResearchOverviewPage from "@/app/research/page";

function envelope(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "1.0",
    source_track: "frozen",
    symbol: "MNQ1!",
    timeframe: "5m",
    generated_at: "2026-07-20T00:00:00Z",
    data_as_of: "2026-06-01T00:00:00Z",
    code_version: "a907325fbb357097fb0e8e064d46772e2b719964",
    warnings: [],
    ...overrides,
  };
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ResearchOverviewPage />
    </QueryClientProvider>,
  );
}

describe("ResearchOverviewPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders both reports' panels and a FROZEN badge once both requests resolve", async () => {
    global.fetch = vi.fn(async (url: string | URL) => {
      const u = String(url);
      if (u.includes("re1/summary")) {
        return new Response(JSON.stringify({ ok: true, envelope: envelope(), report: { fact_profiles: {} } }), { status: 200 });
      }
      if (u.includes("re2/summary")) {
        return new Response(
          JSON.stringify({
            ok: true,
            envelope: envelope({ code_version: "806e4f1ae2386a68207192089ab303d77c05fa66" }),
            report: { setup_profile: {}, time_distribution: {}, overlap: {}, clustering: {}, transitions: {} },
          }),
          { status: 200 },
        );
      }
      throw new Error(`unexpected URL ${u}`);
    }) as unknown as typeof fetch;

    renderWithClient();

    await waitFor(() => expect(screen.getByText("RE-1 Summary")).toBeInTheDocument());
    expect(screen.getByText("RE-2 Summary")).toBeInTheDocument();
    expect(screen.getByText("Time Concentration")).toBeInTheDocument();
    expect(screen.getByText("Overlap Matrix")).toBeInTheDocument();
    expect(screen.getByText("Clustering Summary")).toBeInTheDocument();
    expect(screen.getByText("Transition Summary")).toBeInTheDocument();
    expect(screen.getByText(/FROZEN BASELINE/)).toBeInTheDocument();
  });

  it("shows the mismatch banner and hides panels once the live selector disagrees with the frozen identity", async () => {
    global.fetch = vi.fn(async (url: string | URL) => {
      const u = String(url);
      if (u.includes("re1/summary")) {
        return new Response(JSON.stringify({ ok: true, envelope: envelope(), report: { fact_profiles: {} } }), { status: 200 });
      }
      return new Response(JSON.stringify({ ok: true, envelope: envelope(), report: { setup_profile: {} } }), { status: 200 });
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    renderWithClient();
    await waitFor(() => expect(screen.getByText("RE-1 Summary")).toBeInTheDocument());

    const symbolInput = screen.getByLabelText("Live symbol");
    await user.clear(symbolInput);
    await user.type(symbolInput, "ESU6");

    expect(screen.getByText("Frozen research baseline is available for MNQ1! / 5m.")).toBeInTheDocument();
    expect(screen.queryByText("RE-1 Summary")).not.toBeInTheDocument();
  });
});

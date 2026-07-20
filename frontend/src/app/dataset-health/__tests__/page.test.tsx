import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import DatasetHealthPage from "@/app/dataset-health/page";

function body() {
  return {
    ok: true,
    envelope: {
      schema_version: "1.0",
      source_track: "frozen",
      symbol: "MNQ1!",
      timeframe: "5m",
      generated_at: "2026-07-20T00:00:00Z",
      data_as_of: "2026-06-01T00:00:00Z",
      code_version: "806e4f1ae2386a68207192089ab303d77c05fa66",
      warnings: [],
    },
    dataset_identity: {
      symbol: "MNQ1!",
      timeframe: "5m",
      row_count: 97858,
      date_range: { start: "2025-03-02T23:05:00Z", end: "2026-07-20T11:35:00Z" },
    },
    segment_count: 359,
    certification: {
      checks_run: 27,
      pass_count: 21,
      warning_count: 5,
      fail_count: 1,
      verdict: "rejected",
      checks: [{ section: "0. Ingestion", check: "Row parsing", verdict: "PASS", detail: "ok" }],
    },
    known_warnings: [
      {
        id: "trend-1m-lookback-limit",
        severity: "warning",
        title: "trend_1m unreliable before 2025-07-20",
        detail: "lookback boundary",
        source_document: "docs/market_engine/re1-phase5-freeze.md",
        source_section: "Known limitations, item 1",
      },
    ],
    frozen_version: {
      source_computation_version: "806e4f1ae2386a68207192089ab303d77c05fa66",
      exported_at: "2026-07-20T00:00:00Z",
    },
  };
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DatasetHealthPage />
    </QueryClientProvider>,
  );
}

describe("DatasetHealthPage", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("renders dataset identity, certification, and known warnings", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify(body()), { status: 200 })) as unknown as typeof fetch;
    renderWithClient();

    await waitFor(() => expect(screen.getByText("97,858")).toBeInTheDocument());
    expect(screen.getByText("rejected")).toBeInTheDocument();
    expect(screen.getByText("trend_1m unreliable before 2025-07-20")).toBeInTheDocument();
    expect(screen.getByText(/re1-phase5-freeze\.md/)).toBeInTheDocument();
  });

  it("hides content and shows the mismatch banner once the live selector disagrees", async () => {
    global.fetch = vi.fn(async () => new Response(JSON.stringify(body()), { status: 200 })) as unknown as typeof fetch;
    const user = userEvent.setup();
    renderWithClient();

    await waitFor(() => expect(screen.getByText("97,858")).toBeInTheDocument());

    const timeframeInput = screen.getByLabelText("Live timeframe");
    await user.clear(timeframeInput);
    await user.type(timeframeInput, "1m");

    expect(screen.getByText("Frozen research baseline is available for MNQ1! / 5m.")).toBeInTheDocument();
    expect(screen.queryByText("97,858")).not.toBeInTheDocument();
  });
});

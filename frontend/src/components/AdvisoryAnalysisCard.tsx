"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchLatestAdvisory } from "@/lib/advisoryApi";

const LABELS = {
  long_candidate: "Buy",
  short_candidate: "Sell",
  no_candidate: "No Trade",
  unavailable: "Unavailable",
} as const;

function value(value: number | null): string {
  return value === null ? "Not available" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function AdvisoryAnalysisCard() {
  const query = useQuery({
    queryKey: ["simple-advisory", "MNQ", "5m"],
    queryFn: fetchLatestAdvisory,
    enabled: false,
    retry: false,
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4 lg:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Simple advisory</h2>
          <p className="mt-1 text-xs text-muted">MNQ · 5m · latest verified closed-bar state</p>
        </div>
        <button
          type="button"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
          className="rounded border border-border bg-surface-raised px-3 py-1.5 text-sm font-medium text-foreground disabled:opacity-50"
        >
          {query.isFetching ? "Analyzing…" : "Analyze latest state"}
        </button>
      </div>

      {!query.data && !query.isError && !query.isFetching && (
        <p className="mt-4 text-sm text-muted">Run a manual analysis to inspect the current deterministic setup.</p>
      )}
      {query.isError && (
        <p className="mt-4 text-sm text-danger">Analysis is unavailable. No advisory values were produced.</p>
      )}
      {query.data && (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded border border-border bg-surface-raised px-3 py-1 font-semibold">
              {LABELS[query.data.advisory.state]}
            </span>
            <span className="text-xs text-muted">Freshness: {query.data.advisory.freshness}</span>
            <span className="text-xs text-muted">Data: {query.data.advisory.dataTimestamp ?? "Not available"}</span>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-muted">Entry (confirmation close)</dt><dd>{value(query.data.advisory.entryPrice)}</dd></div>
            <div><dt className="text-xs text-muted">Stop loss</dt><dd>{value(query.data.advisory.stopLoss)}</dd></div>
            <div><dt className="text-xs text-muted">Take profit</dt><dd>{value(query.data.advisory.takeProfit)}</dd></div>
            <div><dt className="text-xs text-muted">Confidence</dt><dd>{query.data.advisory.confidence === null ? "Not available" : query.data.advisory.confidence.toFixed(2)}</dd></div>
          </dl>
          <div className="grid grid-cols-1 gap-2 text-xs text-muted sm:grid-cols-3">
            <p>Setup: {query.data.advisory.setupQuality ?? "Not available"}</p>
            <p>Session: {query.data.advisory.sessionPhase ?? "Not available"}</p>
            <p>Volatility: {query.data.advisory.volatilityRegime ?? "Not available"}</p>
          </div>
          {query.data.advisory.reason && <p className="text-sm text-muted">{query.data.advisory.reason}</p>}
          <div className="rounded border border-border bg-surface-raised p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              {query.data.explanation.status === "available" ? "AI-assisted explanation" : "Deterministic advisory"}
            </p>
            {query.data.explanation.status === "available" ? (
              <div className="mt-2 space-y-2 text-sm">
                <p>{query.data.explanation.summary}</p>
                <ul className="list-disc space-y-1 pl-5">
                  {query.data.explanation.claims.map((claim) => (
                    <li key={claim.claimId}>
                      {claim.text}
                      <span className="block text-xs text-muted">Evidence: {claim.citations.join(", ")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted">AI explanation is unavailable. Deterministic values remain authoritative.</p>
            )}
          </div>
        </div>
      )}

      <p className="mt-5 border-t border-border pt-3 text-xs font-medium text-warn">
        Advisory / paper-only. This view cannot send, modify, or manage orders.
      </p>
    </section>
  );
}

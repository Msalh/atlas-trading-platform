// UI v2, architecture §3.1. The 4 registered Setup Engine setups for Market
// View - sibling to RuleEngineFactsPanel, same neutral-rendering pattern.
// `detected=true` renders as a plain "Active" state, deliberately never
// color-highlighted the way a boolean Rule Engine fact is: architecture §1
// is explicit that "a detected=True setup is displayed as an active
// structural state, never as a signal, alert, or suggestion" - singling
// setups out from facts for that stricter treatment. `severity` (a
// categorical evidence-strength summary, never a score) renders as plain
// text for the same reason.

"use client";

import { useQuery } from "@tanstack/react-query";
import { formatClockCT } from "@/lib/format";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, Setup, SetupEngineLatestResponse, fetchLatestSetupEngineOutput } from "@/lib/setupEngineApi";

function SetupRow({ setup }: { setup: Setup }) {
  const isComputed = setup.status === "computed";
  return (
    <li className={`rounded-md border px-3 py-2 ${isComputed ? "border-border bg-surface" : "border-border bg-surface/50"}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm text-foreground">{setup.name}</span>
        {isComputed ? (
          <span className={setup.detected ? "text-foreground" : "text-muted"}>{setup.detected ? "Active" : "Not active"}</span>
        ) : (
          <span className="text-xs uppercase tracking-wide text-muted">insufficient data</span>
        )}
      </div>
      <div className="mt-1 text-[11px] text-muted">definition v{setup.definition_version}</div>
      {isComputed && setup.detected && setup.severity && (
        <div className="mt-1 text-xs text-muted">evidence strength: {setup.severity}</div>
      )}
      {!isComputed && <p className="mt-1 text-xs text-muted">{setup.reason}</p>}
      {isComputed && (
        <details className="mt-1 text-xs text-muted">
          <summary className="cursor-pointer select-none hover:text-foreground">evidence</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-surface-raised p-2 text-[11px]">
            {JSON.stringify(setup.evidence, null, 2)}
          </pre>
        </details>
      )}
    </li>
  );
}

export function SetupEngineViewer() {
  const { symbol, timeframe } = useLiveSelector();

  const { data, error, isError, isLoading } = useQuery<SetupEngineLatestResponse, ApiFetchError>({
    queryKey: ["market-view-setup-engine-latest", symbol, timeframe],
    queryFn: () => fetchLatestSetupEngineOutput(symbol, timeframe),
    enabled: symbol.trim().length > 0,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Setup Engine</h2>
      {isError && <p className="text-sm text-danger">{error.message}</p>}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && !data.found && (
        <p className="text-sm text-muted">
          No MarketState has been ingested yet for {symbol} / {timeframe}.
        </p>
      )}
      {data?.found && data.data && (
        <>
          <div className="mb-2 text-xs text-muted">Last closed bar: {formatClockCT(data.data.occurred_at)}</div>
          <ol className="space-y-2">
            {data.data.setups.map((setup) => (
              <SetupRow key={setup.name} setup={setup} />
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

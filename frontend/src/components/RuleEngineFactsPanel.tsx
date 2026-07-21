// UI v2, architecture §3.1. The 7 registered Rule Engine facts for Market
// View - same neutral-rendering pattern as the pre-existing
// RuleEngineViewer.tsx (FactRow/FactValue: booleans get a plain Yes/No,
// categorical values render as plain text, "no color-coding implying
// good/bad"), but powered by the shared layout-level live selector and the
// BFF proxy instead of a manually-entered API key - RuleEngineViewer.tsx
// itself is untouched and keeps serving the pre-UI-v2 /rule-engine page.

"use client";

import { useQuery } from "@tanstack/react-query";
import { formatClockCT } from "@/lib/format";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, RuleEngineLatestResponse, fetchLatestRuleEngineOutputViaProxy } from "@/lib/ruleEngineApi";

type Fact = NonNullable<RuleEngineLatestResponse["data"]>["facts"][number];

function FactValue({ value }: { value: boolean | string }) {
  if (typeof value === "boolean") {
    return <span className={value ? "text-ok" : "text-muted"}>{value ? "Yes" : "No"}</span>;
  }
  return <span className="text-foreground">{value}</span>;
}

function FactRow({ fact }: { fact: Fact }) {
  const isComputed = fact.status === "computed";
  return (
    <li className={`rounded-md border px-3 py-2 ${isComputed ? "border-border bg-surface" : "border-border bg-surface/50"}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm text-foreground">{fact.name}</span>
        {isComputed ? (
          <FactValue value={fact.value} />
        ) : (
          <span className="text-xs uppercase tracking-wide text-muted">insufficient data</span>
        )}
      </div>
      <div className="mt-1 text-[11px] text-muted">definition v{fact.definition_version}</div>
      {!isComputed && <p className="mt-1 text-xs text-muted">{fact.reason}</p>}
    </li>
  );
}

export function RuleEngineFactsPanel() {
  const { symbol, timeframe } = useLiveSelector();

  const { data, error, isError, isLoading } = useQuery<RuleEngineLatestResponse, ApiFetchError>({
    queryKey: ["market-view-rule-engine-latest", symbol, timeframe],
    queryFn: () => fetchLatestRuleEngineOutputViaProxy(symbol, timeframe),
    enabled: symbol.trim().length > 0,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Rule Engine Facts</h2>
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
            {data.data.facts.map((fact) => (
              <FactRow key={fact.name} fact={fact} />
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { formatClock, formatTimeAgo } from "@/lib/format";
import {
  RuleEngineFetchError,
  RuleEngineLatestResponse,
  TIMEFRAMES,
  fetchLatestRuleEngineOutput,
  isStale,
} from "@/lib/ruleEngineApi";

const AUTO_REFRESH_INTERVAL_MS = 30_000;

type Fact = NonNullable<RuleEngineLatestResponse["data"]>["facts"][number];

function FactValue({ value }: { value: boolean | string }) {
  if (typeof value === "boolean") {
    return <span className={value ? "text-ok" : "text-muted"}>{value ? "Yes" : "No"}</span>;
  }
  // A categorical fact (e.g. trend_5m's "up"/"down"/"flat") - deliberately
  // rendered as plain, neutral text, no color-coding implying good/bad. This
  // viewer reports facts; judging them is explicitly out of scope (no setup
  // scoring, per the Sprint 16 boundary).
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
      {isComputed && (
        <details className="mt-1 text-xs text-muted">
          <summary className="cursor-pointer select-none hover:text-foreground">evidence</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-surface-raised p-2 text-[11px]">
            {JSON.stringify(fact.evidence, null, 2)}
          </pre>
        </details>
      )}
    </li>
  );
}

export function RuleEngineViewer() {
  const [apiKeyInput, setApiKeyInput] = useState("");
  // Only set once the user explicitly submits the form below - never derived
  // from a keystroke, and never written anywhere but this component's own
  // memory (no localStorage/sessionStorage, no console/log output).
  const [activeApiKey, setActiveApiKey] = useState<string | null>(null);
  const [symbol, setSymbol] = useState("MNQU6");
  const [timeframe, setTimeframe] = useState<string>("5m");
  const [autoRefresh, setAutoRefresh] = useState(false);

  const hasKey = activeApiKey !== null && activeApiKey.length > 0;

  // fetchLatestRuleEngineOutput THROWS RuleEngineFetchError on any non-success
  // outcome (see that module's docstring for why) - this is what makes
  // `data` below "the last successful response" for free, react-query's own
  // native behavior: a failed refetch populates `error`/`isError` without
  // clearing `data`. No hand-rolled "last good" state, no effects, no refs -
  // both of which this repo's lint config forbids using for this purpose.
  const { data, error, isError, isFetching, dataUpdatedAt, refetch } = useQuery<
    RuleEngineLatestResponse,
    RuleEngineFetchError
  >({
    queryKey: ["rule-engine-latest", symbol, timeframe, activeApiKey],
    queryFn: () => fetchLatestRuleEngineOutput(activeApiKey as string, symbol, timeframe),
    enabled: hasKey && symbol.trim().length > 0,
    refetchInterval: autoRefresh && hasKey ? AUTO_REFRESH_INTERVAL_MS : false,
    refetchOnWindowFocus: false,
    // A 401/422 will fail identically every time - retrying just delays
    // showing the user what's actually wrong. Each refresh (manual or
    // polled) is one explicit attempt.
    retry: false,
  });

  function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    if (apiKeyInput.trim().length === 0) return;
    setActiveApiKey(apiKeyInput);
  }

  function handleDisconnect() {
    setActiveApiKey(null);
    setApiKeyInput("");
  }

  const output = data?.data ?? null;
  const stale = output ? isStale(output.occurred_at, output.timeframe) : false;

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">
          Rule Engine Viewer
        </h2>

        {!hasKey ? (
          <form onSubmit={handleConnect} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted" htmlFor="rule-engine-api-key">
                API key
              </label>
              <input
                id="rule-engine-api-key"
                type="password"
                autoComplete="off"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                className="rounded border border-border bg-surface-raised px-2 py-1 text-sm"
                placeholder="Paste your API key"
              />
            </div>
            <button
              type="submit"
              className="rounded border border-open bg-open/10 px-3 py-1 text-sm text-open hover:bg-open/20"
            >
              Connect
            </button>
            <span className="text-xs text-muted">
              Held only in this page&apos;s memory for this session — never stored, never sent
              anywhere except the Authorization header of requests to the Rule Engine endpoint.
            </span>
          </form>
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted" htmlFor="rule-engine-symbol">
                  Symbol
                </label>
                <input
                  id="rule-engine-symbol"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.trim())}
                  className="w-32 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted" htmlFor="rule-engine-timeframe">
                  Timeframe
                </label>
                <select
                  id="rule-engine-timeframe"
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="rounded border border-border bg-surface-raised px-2 py-1 text-sm"
                >
                  {TIMEFRAMES.map((tf) => (
                    <option key={tf} value={tf}>
                      {tf}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => refetch()}
                disabled={isFetching}
                className="rounded border border-open bg-open/10 px-3 py-1 text-sm text-open hover:bg-open/20 disabled:opacity-50"
              >
                {isFetching ? "Refreshing…" : "Refresh"}
              </button>
              <label className="flex items-center gap-2 text-xs text-muted">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                Auto-refresh every 30s (polling)
              </label>
              <button
                type="button"
                onClick={handleDisconnect}
                className="ml-auto text-xs text-muted hover:text-foreground"
              >
                Disconnect
              </button>
            </div>

            <div className="mt-2 text-xs text-muted">
              {dataUpdatedAt > 0
                ? `Last successful refresh: ${formatTimeAgo(new Date(dataUpdatedAt).toISOString())}`
                : isFetching
                  ? "Loading…"
                  : "No successful refresh yet."}
            </div>
          </>
        )}
      </div>

      {hasKey && isError && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {error.message}
          {data && " Showing the last successful result below."}
        </div>
      )}

      {hasKey && isFetching && !data && (
        <p className="text-sm text-muted">Loading…</p>
      )}

      {hasKey && data && !data.found && (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm text-muted">
          No MarketState has been ingested yet for {symbol} / {timeframe}.
        </div>
      )}

      {hasKey && output && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm">
              <span className="text-muted">Latest bar: </span>
              <span className="font-mono text-foreground">{formatClock(output.occurred_at)}</span>
              <span className="ml-2 text-muted">({formatTimeAgo(output.occurred_at)})</span>
            </div>
            <span className="text-[11px] text-muted">schema v{output.schema_version}</span>
          </div>

          {stale && (
            <div className="mb-3 rounded-md border border-warn/40 bg-warn/10 p-2 text-xs text-warn">
              No recent bar — market may be closed or data ingestion may be inactive.
            </div>
          )}

          <ol className="space-y-2">
            {output.facts.map((fact) => (
              <FactRow key={fact.name} fact={fact} />
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

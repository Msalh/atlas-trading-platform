"use client";

import { useQuery } from "@tanstack/react-query";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { RuleEngineFactsPanel } from "@/components/RuleEngineFactsPanel";
import { SetupEngineViewer } from "@/components/SetupEngineViewer";
import { TIMEFRAMES } from "@/lib/ruleEngineApi";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, SetupEngineLatestResponse, fetchLatestSetupEngineOutput } from "@/lib/setupEngineApi";

export default function MarketViewPage() {
  const { symbol, timeframe, setSymbol, setTimeframe } = useLiveSelector();

  // Same query key SetupEngineViewer uses internally - react-query dedupes
  // this into the one shared request/cache entry, so the page-level
  // FreshnessBadge ("LIVE · as of <data_as_of>", architecture §2.1) doesn't
  // cost a second fetch. rule-engine/latest has no envelope of its own
  // (pre-UI-v2 endpoint, unchanged) - setup-engine/latest's is the
  // page-level freshness source; each panel additionally shows its own
  // "Last closed bar" from its own response.
  const { data } = useQuery<SetupEngineLatestResponse, ApiFetchError>({
    queryKey: ["market-view-setup-engine-latest", symbol, timeframe],
    queryFn: () => fetchLatestSetupEngineOutput(symbol, timeframe),
    enabled: symbol.trim().length > 0,
  });
  const envelope = data?.found ? data.envelope : undefined;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-foreground">Market View</h1>
          {envelope && <FreshnessBadge envelope={envelope} />}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="market-view-symbol">
              Symbol
            </label>
            <input
              id="market-view-symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.trim())}
              className="w-28 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="market-view-timeframe">
              Timeframe
            </label>
            <select
              id="market-view-timeframe"
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
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RuleEngineFactsPanel />
        <SetupEngineViewer />
      </div>
    </section>
  );
}

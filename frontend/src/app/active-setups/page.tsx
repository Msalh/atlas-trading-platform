"use client";

import { ActiveSetupBundle } from "@/components/ActiveSetupBundle";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { TIMEFRAMES } from "@/lib/ruleEngineApi";
import { useLiveSelector } from "@/lib/liveSelector";
import { useLiveEpisodes } from "@/lib/useLiveEpisodes";

export default function ActiveSetupsPage() {
  const { symbol, timeframe, setSymbol, setTimeframe } = useLiveSelector();
  // Same query key ActiveSetupBundle's own internal useLiveEpisodes() call
  // uses - react-query dedupes this into the one shared request/cache
  // entry (architecture §9), so the page-level FreshnessBadge doesn't
  // cost a second fetch.
  const { data } = useLiveEpisodes();

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-foreground">Active Setup Bundle</h1>
          {data?.found && <FreshnessBadge envelope={data.envelope} />}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="active-setups-symbol">
              Symbol
            </label>
            <input
              id="active-setups-symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.trim())}
              className="w-28 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="active-setups-timeframe">
              Timeframe
            </label>
            <select
              id="active-setups-timeframe"
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

      <ActiveSetupBundle />
    </section>
  );
}

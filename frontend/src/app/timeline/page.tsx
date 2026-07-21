"use client";

import { Timeline } from "@/components/Timeline";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { TIMEFRAMES } from "@/lib/ruleEngineApi";
import { useLiveSelector } from "@/lib/liveSelector";
import { useLiveEpisodes } from "@/lib/useLiveEpisodes";

export default function TimelinePage() {
  const { symbol, timeframe, setSymbol, setTimeframe } = useLiveSelector();
  // Same query key Timeline's own internal useLiveEpisodes() call uses -
  // react-query dedupes this into one shared request/cache entry.
  const { data } = useLiveEpisodes();

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-foreground">Timeline</h1>
          {data?.found && <FreshnessBadge envelope={data.envelope} />}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="timeline-symbol">
              Symbol
            </label>
            <input
              id="timeline-symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.trim())}
              className="w-28 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="timeline-timeframe">
              Timeframe
            </label>
            <select
              id="timeline-timeframe"
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

      <Timeline />
    </section>
  );
}

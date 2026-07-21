// UI v2, architecture §3.3. A distribution strip for one setup's frozen
// RE-2 episode-duration distribution, with the live duration-so-far
// plotted on the same axis - an explicit historical comparison, never a
// prediction: the "not a prediction" caption is load-bearing text, not
// decoration, per the approved requirement that this strip is "historical
// comparison only, never a projected remaining duration."

import { DurationDistribution } from "@/lib/researchApi";

export interface EpisodeDurationStripProps {
  distribution: DurationDistribution;
  liveDurationBars: number | null;
}

export function EpisodeDurationStrip({ distribution, liveDurationBars }: EpisodeDurationStripProps) {
  const axisMax = Math.max(distribution.max, liveDurationBars ?? 0) || 1;
  const pct = (v: number) => `${Math.min(100, (v / axisMax) * 100)}%`;

  return (
    <div>
      <div className="relative h-6 rounded bg-surface-raised">
        <div
          data-testid="tick-median"
          style={{ left: pct(distribution.median) }}
          className="absolute top-0 h-full w-px bg-muted"
          title={`median: ${distribution.median} bars`}
        />
        <div
          data-testid="tick-p75"
          style={{ left: pct(distribution.p75) }}
          className="absolute top-0 h-full w-px bg-muted"
          title={`p75: ${distribution.p75} bars`}
        />
        <div
          data-testid="tick-p90"
          style={{ left: pct(distribution.p90) }}
          className="absolute top-0 h-full w-px bg-muted"
          title={`p90: ${distribution.p90} bars`}
        />
        <div
          data-testid="tick-p95"
          style={{ left: pct(distribution.p95) }}
          className="absolute top-0 h-full w-px bg-muted"
          title={`p95: ${distribution.p95} bars`}
        />
        {liveDurationBars !== null && (
          <div
            data-testid="live-duration-marker"
            style={{ left: pct(liveDurationBars) }}
            className="absolute top-0 h-full w-0.5 bg-open"
            title={`current episode: ${liveDurationBars} bars so far`}
          />
        )}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted">
        <span>0</span>
        <span>median {distribution.median}</span>
        <span>p90 {distribution.p90}</span>
        <span>max {distribution.max}</span>
      </div>
      <p className="mt-2 text-[11px] text-muted">
        Historical comparison across {distribution.count} episodes — not a prediction of remaining duration.
      </p>
    </div>
  );
}

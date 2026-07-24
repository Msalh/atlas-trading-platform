"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAnalyticsSummary } from "@/lib/analyticsApi";
import { formatPct, formatPnl, formatRatio } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

function Stat({
  label,
  value,
  valueClass,
  sub,
}: {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="text-[11px] uppercase text-muted">{label}</div>
      <div className={`mt-1 font-mono text-xl ${valueClass ?? ""}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function AnalyticsSummaryCards() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["analytics", "summary"],
    queryFn: fetchAnalyticsSummary,
    refetchInterval: pollInterval(sseConnected, 30_000),
  });

  if (isLoading) return <p className="text-sm text-muted">Loading…</p>;
  if (isError) return <p className="text-sm text-danger">Could not load analytics summary.</p>;
  if (!data) return null;

  if (data.total_trades === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border py-8 text-center text-sm text-muted">
        No closed trades yet - analytics will populate as trades close.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <Stat label="Trades" value={String(data.total_trades)} sub={`${data.wins}W / ${data.losses}L`} />
      <Stat label="Win Rate" value={formatPct(data.win_rate_pct)} />
      <Stat
        label="Profit Factor"
        value={data.profit_factor === null ? "∞" : formatRatio(data.profit_factor)}
      />
      <Stat
        label="Expectancy"
        value={formatPnl(data.expectancy)}
        valueClass={data.expectancy >= 0 ? "text-long" : "text-short"}
      />
      <Stat
        label="Avg R"
        value={data.avg_r === null ? "-" : `${formatRatio(data.avg_r)}R`}
        valueClass={data.avg_r !== null ? (data.avg_r >= 0 ? "text-long" : "text-short") : ""}
        sub={`n=${data.r_multiple_sample_size}`}
      />
      <Stat
        label="Avg Win / Loss"
        value={`${formatPnl(data.avg_win)} / ${formatPnl(data.avg_loss)}`}
      />
    </div>
  );
}

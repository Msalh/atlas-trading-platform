"use client";

import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { formatDateShort, formatPnl } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

export function DrawdownChart() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["analytics", "equity-curve"],
    queryFn: api.equityCurve,
    refetchInterval: pollInterval(sseConnected, 30_000),
  });

  // Plotted as negative values ("underwater equity curve") so the chart dips below a
  // zero baseline - the conventional way to read a drawdown chart at a glance.
  const chartData = data?.points.map((p) => ({ closed_at: p.closed_at, drawdown: -p.drawdown })) ?? [];

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wide">Drawdown</h2>
        {data && data.points.length > 0 && (
          <span className="font-mono text-xs text-danger">
            Max {formatPnl(-data.max_drawdown)} ({data.max_drawdown_pct.toFixed(1)}%)
          </span>
        )}
      </div>
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load the drawdown curve.</p>}
      {data && data.points.length === 0 && (
        <p className="py-8 text-center text-sm text-muted">No closed trades yet.</p>
      )}
      {data && data.points.length > 0 && (
        <div className="h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="drawdownFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-danger)" stopOpacity={0} />
                  <stop offset="100%" stopColor="var(--color-danger)" stopOpacity={0.35} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="closed_at"
                tickFormatter={(v: string) => formatDateShort(v)}
                stroke="var(--color-muted)"
                fontSize={11}
              />
              <YAxis stroke="var(--color-muted)" fontSize={11} tickFormatter={(v: number) => v.toLocaleString()} width={70} />
              <Tooltip
                contentStyle={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  fontSize: 12,
                }}
                labelFormatter={(label) => formatDateShort(label as string)}
                formatter={(value) => [formatPnl(Number(value)), "Drawdown"]}
              />
              <Area
                type="monotone"
                dataKey="drawdown"
                stroke="var(--color-danger)"
                fill="url(#drawdownFill)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

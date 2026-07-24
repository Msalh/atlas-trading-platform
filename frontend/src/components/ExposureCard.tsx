"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchRisk } from "@/lib/riskApi";
import { formatPnl, formatPoints, formatPrice } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";
import { DirectionBadge } from "@/components/StatusBadge";
import { RiskProgressBar } from "@/components/RiskProgressBar";

export function ExposureCard() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["risk"],
    queryFn: fetchRisk,
    refetchInterval: pollInterval(sseConnected, 5_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-muted uppercase tracking-wide">
        Current Exposure &amp; Position Sizing
      </h2>
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isError && <p className="text-sm text-danger">Could not load exposure data.</p>}

      {data && !data.open_position && (
        <div className="flex items-center justify-center rounded-md border border-dashed border-border py-6 text-sm text-muted">
          Flat — no exposure.
        </div>
      )}

      {data?.open_position && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DirectionBadge direction={data.open_position.direction} />
              <span className="font-mono text-sm text-muted">
                {data.open_position.quantity ?? "?"} contract
                {data.open_position.quantity === 1 ? "" : "s"}
              </span>
            </div>
            {data.open_position.exceeds_max_contracts && (
              <span className="rounded-full border border-danger/40 bg-danger/10 px-2 py-0.5 text-[11px] font-semibold text-danger">
                exceeds max
              </span>
            )}
          </div>

          {data.open_position.quantity !== null && (
            <div>
              <div className="mb-1 flex justify-between text-xs text-muted">
                <span>Position sizing</span>
                <span>
                  {data.open_position.quantity} / {data.max_contracts} contracts
                </span>
              </div>
              <RiskProgressBar
                usedPct={data.open_position.exposure_pct_of_max ?? 0}
                breached={data.open_position.exceeds_max_contracts}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 rounded-md bg-surface-raised p-3 font-mono text-sm">
            <div>
              <div className="text-[11px] uppercase text-muted">Unrealized risk</div>
              <div className="text-short">
                {formatPoints(data.open_position.risk_points)} pts
                {data.open_position.risk_dollars !== null && (
                  <span> ({formatPnl(-data.open_position.risk_dollars)})</span>
                )}
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase text-muted">Unrealized reward</div>
              <div className="text-long">
                {formatPoints(data.open_position.reward_points)} pts
                {data.open_position.reward_dollars !== null && (
                  <span> ({formatPnl(data.open_position.reward_dollars)})</span>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-between text-xs text-muted">
            <span>Entry {formatPrice(data.open_position.entry_price)}</span>
            <span>Current {formatPrice(data.open_position.current_price)}</span>
            <span
              className={
                (data.open_position.unrealized_pnl ?? 0) >= 0 ? "text-long" : "text-short"
              }
            >
              Unrealized P&amp;L {formatPnl(data.open_position.unrealized_pnl)}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}

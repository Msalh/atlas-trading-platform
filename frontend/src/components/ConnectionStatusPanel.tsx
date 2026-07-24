"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStatus } from "@/lib/statusApi";
import { formatTimeAgo } from "@/lib/format";
import { pollInterval } from "@/lib/intervals";
import { useLiveUpdatesConnected } from "@/lib/live-updates";

function Row({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean | null;
  detail: string;
}) {
  const color = ok === null ? "bg-muted" : ok ? "bg-ok" : "bg-danger";
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 shrink-0 rounded-full ${color}`} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <span className="text-right text-xs text-muted">{detail}</span>
    </div>
  );
}

export function ConnectionStatusPanel() {
  const sseConnected = useLiveUpdatesConnected();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["status"],
    queryFn: fetchStatus,
    refetchInterval: pollInterval(sseConnected, 10_000),
  });

  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 text-sm font-semibold text-muted uppercase tracking-wide">
        Connection Status
      </h2>
      {isLoading && <p className="py-4 text-sm text-muted">Loading…</p>}
      {isError && <p className="py-4 text-sm text-danger">Could not reach the Atlas backend.</p>}
      {data && (
        <div className="divide-y divide-border">
          <Row label="Database" ok={data.database.ok} detail={data.database.detail} />
          <Row
            label="TradingView"
            ok={data.tradingview.last_webhook_at !== null}
            detail={
              data.tradingview.last_webhook_at
                ? `last seen ${formatTimeAgo(data.tradingview.last_webhook_at)}`
                : "no webhooks since restart"
            }
          />
          <Row
            label="PickMyTrade"
            ok={!data.pickmytrade.configured ? null : data.pickmytrade.last_forward_ok}
            detail={
              !data.pickmytrade.configured
                ? "not configured"
                : data.pickmytrade.last_forward_at
                  ? data.pickmytrade.last_forward_ok
                    ? `forwarded ${formatTimeAgo(data.pickmytrade.last_forward_at)}`
                    : `failed ${formatTimeAgo(data.pickmytrade.last_forward_at)}: ${data.pickmytrade.last_error ?? "unknown error"}`
                  : "no forwards since restart"
            }
          />
          <Row
            label="Claude"
            ok={!data.claude.configured ? null : data.claude.last_error === null ? true : false}
            detail={
              !data.claude.configured
                ? "not configured"
                : data.claude.last_analysis_at
                  ? data.claude.last_error
                    ? `error ${formatTimeAgo(data.claude.last_analysis_at)}: ${data.claude.last_error}`
                    : `analyzed ${formatTimeAgo(data.claude.last_analysis_at)}`
                  : "no analysis since restart"
            }
          />
        </div>
      )}
      <p className="mt-3 text-[11px] text-muted">
        TradingView/PickMyTrade/Claude activity resets on every backend restart — this
        reflects activity since the process last started, not all-time history.
      </p>
    </section>
  );
}

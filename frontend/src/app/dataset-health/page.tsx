"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { MismatchBanner, isSymbolTimeframeMismatch } from "@/components/MismatchBanner";
import { CertificationTable } from "@/components/DatasetHealthPanels/CertificationTable";
import { KnownWarningsList } from "@/components/DatasetHealthPanels/KnownWarningsList";
import { formatDateShort } from "@/lib/format";
import { ApiFetchError, fetchDatasetHealth } from "@/lib/researchApi";

export default function DatasetHealthPage() {
  // Page-local stand-in for the shared, layout-level LIVE symbol/timeframe
  // selector (architecture §8) - see research/page.tsx's own note; the same
  // deliberately-deferred placeholder, replaced once F5 (Market View,
  // Stage 2) ships the real shared selector.
  const [liveSymbol, setLiveSymbol] = useState("MNQ1!");
  const [liveTimeframe, setLiveTimeframe] = useState("5m");

  const { data, error, isError, isLoading } = useQuery<Awaited<ReturnType<typeof fetchDatasetHealth>>, ApiFetchError>({
    queryKey: ["research-dataset-health"],
    queryFn: fetchDatasetHealth,
  });

  const mismatched =
    data !== undefined &&
    isSymbolTimeframeMismatch(data.dataset_identity.symbol, data.dataset_identity.timeframe, liveSymbol, liveTimeframe);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Dataset Health</h1>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="dataset-health-live-symbol">
              Live symbol
            </label>
            <input
              id="dataset-health-live-symbol"
              value={liveSymbol}
              onChange={(e) => setLiveSymbol(e.target.value.trim())}
              className="w-28 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="dataset-health-live-timeframe">
              Live timeframe
            </label>
            <input
              id="dataset-health-live-timeframe"
              value={liveTimeframe}
              onChange={(e) => setLiveTimeframe(e.target.value.trim())}
              className="w-20 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
        </div>
      </div>

      {data && (
        <MismatchBanner
          frozenSymbol={data.dataset_identity.symbol}
          frozenTimeframe={data.dataset_identity.timeframe}
          liveSymbol={liveSymbol}
          liveTimeframe={liveTimeframe}
        />
      )}

      {isError && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error.message}</div>
      )}

      {isLoading && <p className="text-sm text-muted">Loading…</p>}

      {!mismatched && data && (
        <>
          <FreshnessBadge envelope={data.envelope} />

          <div className="rounded-lg border border-border bg-surface p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Dataset Identity</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-xs text-muted">Symbol</dt>
                <dd className="font-mono text-foreground">{data.dataset_identity.symbol}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Timeframe</dt>
                <dd className="font-mono text-foreground">{data.dataset_identity.timeframe}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Row count</dt>
                <dd className="text-foreground">{data.dataset_identity.row_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Segments</dt>
                <dd className="text-foreground">{data.segment_count}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-muted">Date range</dt>
                <dd className="text-foreground">
                  {formatDateShort(data.dataset_identity.date_range.start)} – {formatDateShort(data.dataset_identity.date_range.end)}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-muted">Frozen computation</dt>
                <dd className="font-mono text-foreground">
                  {data.frozen_version.source_computation_version?.slice(0, 7) ?? "unknown"} (exported{" "}
                  {formatDateShort(data.frozen_version.exported_at)})
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-lg border border-border bg-surface p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Certification</h2>
            <CertificationTable certification={data.certification} />
          </div>

          <div className="rounded-lg border border-border bg-surface p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Known Warnings</h2>
            <KnownWarningsList warnings={data.known_warnings} />
          </div>
        </>
      )}
    </section>
  );
}

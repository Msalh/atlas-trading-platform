"use client";

import { useQuery } from "@tanstack/react-query";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { MismatchBanner, isSymbolTimeframeMismatch } from "@/components/MismatchBanner";
import { CertificationTable } from "@/components/DatasetHealthPanels/CertificationTable";
import { KnownWarningsList } from "@/components/DatasetHealthPanels/KnownWarningsList";
import { formatDateShortCT } from "@/lib/format";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, fetchDatasetHealth } from "@/lib/researchApi";

export default function DatasetHealthPage() {
  // The shared, layout-level LIVE symbol/timeframe selector (architecture
  // §8, F5).
  const { symbol: liveSymbol, timeframe: liveTimeframe } = useLiveSelector();

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
        <span className="text-xs text-muted">
          Current live selection: <span className="font-mono text-foreground">{liveSymbol}</span> /{" "}
          <span className="font-mono text-foreground">{liveTimeframe}</span>
        </span>
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
                  {formatDateShortCT(data.dataset_identity.date_range.start)} – {formatDateShortCT(data.dataset_identity.date_range.end)}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-muted">Frozen computation</dt>
                <dd className="font-mono text-foreground">
                  {data.frozen_version.source_computation_version?.slice(0, 7) ?? "unknown"} (exported{" "}
                  {formatDateShortCT(data.frozen_version.exported_at)})
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

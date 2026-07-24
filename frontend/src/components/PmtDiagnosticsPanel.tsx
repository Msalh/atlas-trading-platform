import type { PmtRelayDiagnostics } from "@/lib/tradesApi";
import { formatClock } from "@/lib/format";

// Debug-only panel showing the latest PickMyTrade relay attempt in full - added
// specifically to inspect the normalized data/price/date fields and PickMyTrade's raw
// response without needing to curl the API directly. Read-only, no business logic.
export function PmtDiagnosticsPanel({ diagnostics }: { diagnostics: PmtRelayDiagnostics }) {
  const failed = Boolean(diagnostics.exception) || (diagnostics.status_code ?? 0) >= 400;

  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <h2 className="mb-4 text-sm font-semibold text-muted uppercase tracking-wide">
        PickMyTrade Relay Diagnostics
      </h2>

      <div className="grid grid-cols-2 gap-4 font-mono text-xs sm:grid-cols-4">
        <div>
          <div className="text-[11px] uppercase text-muted">Attempted</div>
          <div>{formatClock(diagnostics.attempted_at)}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase text-muted">Status code</div>
          <div className={failed ? "text-danger" : "text-ok"}>{diagnostics.status_code ?? "-"}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase text-muted">Duration</div>
          <div>{diagnostics.duration_ms}ms</div>
        </div>
        <div className="truncate" title={diagnostics.url ?? undefined}>
          <div className="text-[11px] uppercase text-muted">URL</div>
          <div>{diagnostics.url ?? "-"}</div>
        </div>
      </div>

      {diagnostics.exception && (
        <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {diagnostics.exception}
        </p>
      )}

      <div className="mt-4 grid grid-cols-3 gap-4 rounded-md bg-surface-raised p-3 font-mono text-xs">
        <div>
          <div className="text-[11px] uppercase text-muted">data (normalized)</div>
          <div>{String(diagnostics.payload?.data ?? "-")}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase text-muted">price (normalized)</div>
          <div>{String(diagnostics.payload?.price ?? "-")}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase text-muted">date (normalized)</div>
          <div>{String(diagnostics.payload?.date ?? "-")}</div>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-1 text-[11px] uppercase text-muted">Response body</div>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md bg-surface-raised p-3 font-mono text-xs">
          {diagnostics.response_body ?? "-"}
        </pre>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-[11px] uppercase text-muted">
          Full normalized payload sent
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md bg-surface-raised p-3 font-mono text-xs">
          {JSON.stringify(diagnostics.payload, null, 2)}
        </pre>
      </details>
    </section>
  );
}

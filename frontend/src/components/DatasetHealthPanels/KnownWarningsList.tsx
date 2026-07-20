// UI v2, architecture §5.3/§3.6. Every disclosed limitation of the frozen
// baseline, shown as a typed, traceable KnownWarning - source_document and
// source_section are rendered directly (not hidden behind a click) so the
// approved requirement ("must remain visible or accessible in the UI") is
// met unambiguously.

import { KnownWarning } from "@/lib/researchApi";

const SEVERITY_STYLE: Record<string, string> = {
  warning: "border-warn/40 bg-warn/10 text-warn",
  fail: "border-danger/40 bg-danger/10 text-danger",
};

export function KnownWarningsList({ warnings }: { warnings: KnownWarning[] }) {
  if (warnings.length === 0) {
    return <p className="text-sm text-muted">No known warnings disclosed for this baseline.</p>;
  }

  return (
    <ul className="space-y-2">
      {warnings.map((warning) => (
        <li key={warning.id} className="rounded-md border border-border bg-surface px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-foreground">{warning.title}</span>
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
                SEVERITY_STYLE[warning.severity] ?? "border-border bg-surface-raised text-muted"
              }`}
            >
              {warning.severity}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">{warning.detail}</p>
          <p className="mt-1 text-[11px] text-muted">
            Source: {warning.source_document} — {warning.source_section}
          </p>
        </li>
      ))}
    </ul>
  );
}

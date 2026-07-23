// Sprint 10 Slice B. A small, reusable status card - overall Research
// status and the detailed Ledger check breakdown both use this, rather
// than each hand-rolling their own markup. Mirrors ConnectionStatusPanel's
// own Row pattern (dot + label + detail) exactly, the closest existing
// precedent in this codebase for "a short list of named health checks."

export type ReadinessStatus = "ok" | "degraded" | "unreachable";

const STATUS_DOT_COLOR: Record<ReadinessStatus, string> = {
  ok: "bg-ok",
  degraded: "bg-warn",
  unreachable: "bg-danger",
};

export interface ReadinessCheck {
  label: string;
  ok: boolean;
  detail?: string | null;
}

export interface ReadinessCardProps {
  title: string;
  status: ReadinessStatus;
  statusLabel: string;
  detail?: string | null;
  checks?: ReadinessCheck[];
}

export function ReadinessCard({ title, status, statusLabel, detail, checks }: ReadinessCardProps) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT_COLOR[status]}`} />
        <span className="text-sm font-medium text-foreground">{statusLabel}</span>
      </div>
      {detail && <p className="mt-1 text-xs text-muted">{detail}</p>}
      {checks && checks.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
          {checks.map((check) => (
            <li key={check.label} className="flex items-center justify-between gap-2 text-xs">
              <span className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${check.ok ? "bg-ok" : "bg-danger"}`} />
                <span className="text-foreground">{check.label}</span>
              </span>
              {check.detail && <span className="text-muted">{check.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Sprint 10 Slice B. A small, reusable stat tile - Latest Snapshot, Latest
// Validation, and Promotion count all use this. Observability only: a
// label, one headline value, and an optional line of supporting detail -
// deliberately nothing clickable, editable, or tabular here (Sprint 10's
// own "Operations Dashboard, not Management Console" principle).

export interface StatCardProps {
  label: string;
  value: string;
  detail?: string | null;
  /** Rendered instead of `value`/`detail` when there is nothing to show yet
   * (e.g. no snapshot has ever been recorded) - a distinct, calm state,
   * never styled as an error. */
  empty?: string | null;
}

export function StatCard({ label, value, detail, empty }: StatCardProps) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{label}</h2>
      {empty ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <>
          <p className="font-mono text-sm text-foreground break-all">{value}</p>
          {detail && <p className="mt-1 text-xs text-muted">{detail}</p>}
        </>
      )}
    </section>
  );
}

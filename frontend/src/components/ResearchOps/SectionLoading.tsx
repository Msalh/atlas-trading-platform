// Sprint 10 Slice G (consistency consolidation). Extracted from six
// identical local copies (Overview, Leaderboard, Snapshot Explorer,
// Promotion Queue, Promotion History, Run Center all defined the exact
// same function verbatim) - the summary-strip "this card's data hasn't
// resolved yet" placeholder every ResearchOps page uses in place of a
// StatCard/ReadinessCard while its own query is still pending.

export function SectionLoading({ title }: { title: string }) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      <p className="text-sm text-muted">Loading…</p>
    </section>
  );
}

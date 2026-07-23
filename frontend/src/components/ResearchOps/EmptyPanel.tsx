// Sprint 10 Slice G (consistency consolidation). Extracted from four
// identical local copies (Leaderboard, Snapshot Explorer, Promotion
// Queue, Promotion History all defined the exact same function verbatim)
// - a single-message content-area panel used for empty states, degraded-
// ledger errors (tone="error"), and - since its default styling is
// byte-identical to the inline "Loading…" div every one of those same
// four pages also duplicated - the primary-content-area loading state
// too (`<EmptyPanel message="Loading…" />`), removing a second, smaller
// duplication at the same time.

export function EmptyPanel({ message, tone = "default" }: { message: string; tone?: "default" | "error" }) {
  return (
    <div
      className={`rounded-lg border p-4 text-sm ${
        tone === "error" ? "border-danger/40 bg-danger/10 text-danger" : "border-border bg-surface text-muted"
      }`}
    >
      {message}
    </div>
  );
}

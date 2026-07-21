// UI v2. Generic, collapsible display of one frozen report section - the
// same posture as RuleEngineViewer's own fact-evidence <details><pre> block
// (this repo's established precedent for showing a raw, already-computed
// structure without inventing new derived analytics on top of it). Used for
// every Research Overview panel since RE-1/RE-2 report bodies are large,
// free-form, and produced entirely by atlas/research_export/snapshot_builder.py -
// nothing here recomputes or reinterprets a single figure.

export function JsonSection({ title, description, data }: { title: string; description?: string; data: unknown }) {
  return (
    <details className="rounded-lg border border-border bg-surface p-4" open>
      <summary className="cursor-pointer select-none text-sm font-semibold uppercase tracking-wide text-muted">
        {title}
      </summary>
      {description && <p className="mt-2 text-xs text-muted">{description}</p>}
      <pre className="mt-3 max-h-96 overflow-auto rounded bg-surface-raised p-3 text-[11px] text-foreground">
        {JSON.stringify(data, null, 2) ?? "null"}
      </pre>
    </details>
  );
}

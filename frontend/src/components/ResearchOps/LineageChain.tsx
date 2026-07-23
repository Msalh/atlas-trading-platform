// Sprint 10 Slice D. A generic, domain-agnostic vertical chain renderer -
// deliberately knows nothing about Hypothesis/Realization/Experiment/
// Evidence/Validation/Promotion. The Snapshot Explorer page owns every
// Research-Engine-specific label, field choice, and formatting decision;
// this component only knows how to lay out an ordered list of named
// stages, each holding zero or more items, each item either a small
// labeled field list or an explicit empty/missing state. Kept generic per
// the Slice D kickoff's own instruction ("keep it generic enough for
// future reuse") - nothing here would need to change to render, say, a
// future Run Center's own provenance chain.

export interface LineageNodeField {
  label: string;
  value: string;
}

export interface LineageNodeItem {
  title: string;
  fields: LineageNodeField[];
  badge?: { label: string; tone: "ok" | "warn" | "danger" | "neutral" };
}

export interface LineageNode {
  /** Stage label, e.g. "Hypothesis", "Realization". */
  label: string;
  /** Zero or more instances at this stage - empty renders `emptyMessage`. */
  items: LineageNodeItem[];
  /** Shown instead of any item card when `items` is empty. */
  emptyMessage: string;
}

const BADGE_TONE_STYLE: Record<NonNullable<LineageNodeItem["badge"]>["tone"], string> = {
  ok: "border-open/30 bg-open/15 text-open",
  warn: "border-warn/30 bg-warn/15 text-warn",
  danger: "border-danger/30 bg-danger/15 text-danger",
  neutral: "border-border bg-surface-raised text-muted",
};

export function LineageChain({ nodes }: { nodes: LineageNode[] }) {
  return (
    <ol className="space-y-0">
      {nodes.map((node, index) => (
        <li key={node.label}>
          <div className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-xs font-semibold text-muted">
                {index + 1}
              </span>
              {index < nodes.length - 1 && <span className="w-px flex-1 bg-border" />}
            </div>
            <div className="min-w-0 flex-1 pb-6">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{node.label}</h3>
              {node.items.length === 0 ? (
                <p className="rounded-lg border border-border bg-surface p-3 text-sm text-muted">{node.emptyMessage}</p>
              ) : (
                <div className="space-y-2">
                  {node.items.map((item, itemIndex) => (
                    <div key={`${item.title}-${itemIndex}`} className="rounded-lg border border-border bg-surface p-3">
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span className="font-mono text-sm text-foreground">{item.title}</span>
                        {item.badge && (
                          <span
                            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${BADGE_TONE_STYLE[item.badge.tone]}`}
                          >
                            {item.badge.label}
                          </span>
                        )}
                      </div>
                      {item.fields.length > 0 && (
                        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                          {item.fields.map((field) => (
                            <div key={field.label} className="flex items-baseline justify-between gap-2 text-xs">
                              <dt className="text-muted">{field.label}</dt>
                              <dd className="truncate font-mono text-foreground">{field.value}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

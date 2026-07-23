// Sprint 10 Slice F. A card describing one entry in the Research Engine's
// operation catalog - informational only, per the Run Center's own scope
// (no execute buttons, no disabled-button placeholders, no fake controls).
// New here because no existing ResearchOps component fits this shape:
// PromotionStatusBadge is typed to EntryPromotionStatus (a promotion
// decision), not an operation's availability, and forcing that reuse would
// conflate two different domains for no real benefit. This card's own
// fields (name, description, availability, a prerequisites list, current
// state) are generic enough that a future slice adding real execution
// controls could extend this same card with an action area, rather than
// replacing it - the "clear long-term value" bar the Slice F kickoff asks
// new components to clear.
//
// `availability` is four states, not a binary, because the Run Center's
// five cataloged operations are NOT all the same kind of thing:
// - "available"/"unavailable": Research Run (mode=smoke) is a real,
//   POST-triggerable operation gated only by Research Ledger readiness
//   (atlas/api/v1/research_pipeline.py's own _degraded_response check).
// - "not_implemented": Replay/Benchmark are declared modes
//   (_RUN_MODES) with no implementation (_IMPLEMENTED_MODES) - the
//   backend's own run_research() rejects them with a 501 unconditionally,
//   BEFORE it even checks Ledger readiness. A degraded/healthy Ledger
//   makes no difference to these two - collapsing this into "unavailable"
//   would misrepresent it as a transient, ledger-driven state rather than
//   a fixed, not-yet-built one.
// - "not_standalone": Validation and Promotion Review are not
//   independently invocable via any endpoint at all - Validation is a
//   pure computation stage embedded inside Research Run
//   (atlas.research.validation.service.validate(), always pure/no-I/O by
//   design since Sprint 6); Promotion Review is a human decision workflow
//   (the Slice E Queue/History pages), not a system operation with a
//   trigger. Neither "available" nor "unavailable" honestly describes
//   something that was never meant to be triggered on its own.

const AVAILABILITY_DOT_COLOR: Record<OperationAvailability, string> = {
  available: "bg-ok",
  unavailable: "bg-danger",
  not_implemented: "bg-muted",
  not_standalone: "bg-muted",
};

const AVAILABILITY_LABEL: Record<OperationAvailability, string> = {
  available: "Available",
  unavailable: "Unavailable",
  not_implemented: "Not Implemented",
  not_standalone: "Not a Standalone Operation",
};

export type OperationAvailability = "available" | "unavailable" | "not_implemented" | "not_standalone";

export interface OperationCardProps {
  name: string;
  description: string;
  availability: OperationAvailability;
  availabilityDetail?: string | null;
  prerequisites: string[];
  state: string;
}

export function OperationCard({ name, description, availability, availabilityDetail, prerequisites, state }: OperationCardProps) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{name}</h3>
          <p className="mt-1 text-xs text-muted">{description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${AVAILABILITY_DOT_COLOR[availability]}`} />
          <span className="text-xs font-medium text-foreground">{AVAILABILITY_LABEL[availability]}</span>
        </div>
      </div>
      {availabilityDetail && <p className="mt-1 text-xs text-muted">{availabilityDetail}</p>}

      <div className="mt-3 border-t border-border pt-3">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted">Prerequisites</h4>
        {prerequisites.length === 0 ? (
          <p className="mt-1 text-xs text-muted">None</p>
        ) : (
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-foreground">
            {prerequisites.map((prerequisite) => (
              <li key={prerequisite}>{prerequisite}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-3 border-t border-border pt-3">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted">Current State</h4>
        <p className="mt-1 text-xs text-foreground">{state}</p>
      </div>
    </section>
  );
}

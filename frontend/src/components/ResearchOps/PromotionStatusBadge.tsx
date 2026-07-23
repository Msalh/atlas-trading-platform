// Sprint 10 Slice C. A small, reusable badge for a promotion decision
// state - "pending" (no PromotionRecord exists yet for this hypothesis/
// realization pair) plus the three real PromotionDecision values. Built
// here because the Leaderboard table needs it now, and Slice E's own
// Promotion Queue/History pages will need the identical status→color
// mapping - factored out once rather than duplicated per page.
//
// Sprint 10 Slice E.1: optional `label` override added. Color is always
// driven by `status` (a Queue-context "declined" candidate is still, in
// truth, a declined one - the styling shouldn't change), but the Queue
// page overrides the displayed text to "Previously Declined" for that one
// status, per the certification review's own semantic clarification: a
// DECLINED PromotionRecord does not exclude a candidate from the queue
// (see atlas.research.promotion.service.list_promotion_candidates()), so
// the bare word "Declined" inside a page titled "Promotion Queue" read as
// contradictory. deriveCandidateStatus() and the backend's own decision
// value are both unchanged - this is presentation-only, and only the
// Queue page opts into it. Promotion History passes no override, so it
// keeps rendering the immutable decision as plain "Declined".

import { EntryPromotionStatus } from "@/lib/researchOpsApi";

const STATUS_STYLE: Record<EntryPromotionStatus, string> = {
  pending: "border-border bg-surface-raised text-muted",
  approved: "border-open/30 bg-open/15 text-open",
  declined: "border-danger/30 bg-danger/15 text-danger",
  deferred: "border-warn/30 bg-warn/15 text-warn",
};

const STATUS_LABEL: Record<EntryPromotionStatus, string> = {
  pending: "Pending Review",
  approved: "Approved",
  declined: "Declined",
  deferred: "Deferred",
};

export function PromotionStatusBadge({ status, label }: { status: EntryPromotionStatus; label?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${STATUS_STYLE[status]}`}
    >
      {label ?? STATUS_LABEL[status]}
    </span>
  );
}

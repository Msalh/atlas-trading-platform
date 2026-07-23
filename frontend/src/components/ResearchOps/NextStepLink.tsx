// Sprint 10 Slice G. A small, consistent "what's the next relevant page"
// affordance - the kickoff's own objective 4 ("Ensure every page can
// naturally reach the next relevant page"), distinct from the global top
// nav (objective 2, which makes every page reachable but doesn't suggest
// an order). Placed once per page next to the existing subtitle, in the
// established workflow order: Overview -> Leaderboard -> Snapshot
// Explorer -> Promotion Queue -> Promotion History -> Run Center. Run
// Center, the last step, renders none.

import Link from "next/link";

export function NextStepLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="text-xs text-muted hover:text-foreground">
      Next: {label} →
    </Link>
  );
}

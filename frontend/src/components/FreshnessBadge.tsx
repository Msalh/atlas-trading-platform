// UI v2. Shown on every screen (architecture §2/§6) so the dashboard never
// implies the FROZEN research baseline reflects "now." Reads provenance
// exclusively from the response envelope's own fields - never infers
// LIVE-vs-FROZEN, a date, or a version from which endpoint was called.
// `envelope.code_version` is always `source_computation_version`, never
// `snapshot_exporter_version` - enforced by the backend (atlas/api/v1/
// research.py's `_http_envelope`), not re-derived here.
//
// Production-hardening amendment 5: a reachable API with an old
// data_as_of must never keep showing an unqualified LIVE badge. The live
// branch now classifies freshness (lib/freshness.ts) and renders one of
// three distinct states - "LIVE — LAST CLOSED BAR" is shown ONLY when
// current; delayed/stale get a visibly different label and color, never
// the same green "as if nothing's wrong" treatment. The remaining two
// operational states (no_data, disconnected) are NOT this component's
// concern - every caller already has its own dedicated branch for
// "nothing ingested yet" / "the fetch failed" that renders instead of a
// FreshnessBadge, not alongside one.

import { classifyFreshness } from "@/lib/freshness";
import { ResponseEnvelope } from "@/lib/apiEnvelope";
import { formatClockCT, formatDateShortCT } from "@/lib/format";

const LIVE_STATE_STYLE: Record<string, string> = {
  current: "border-open/30 bg-open/15 text-open",
  delayed: "border-warn/30 bg-warn/15 text-warn",
  stale: "border-danger/30 bg-danger/15 text-danger",
};

const LIVE_STATE_LABEL: Record<string, string> = {
  current: "LIVE — LAST CLOSED BAR",
  delayed: "LIVE — DELAYED",
  stale: "LIVE — STALE",
};

export function FreshnessBadge({ envelope }: { envelope: ResponseEnvelope }) {
  if (envelope.source_track === "live") {
    const state = classifyFreshness(envelope.data_as_of, envelope.timeframe);
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${LIVE_STATE_STYLE[state]}`}
      >
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
        {LIVE_STATE_LABEL[state]} · as of {formatClockCT(envelope.data_as_of)}
      </span>
    );
  }

  const shortSha = envelope.code_version ? envelope.code_version.slice(0, 7) : "unknown";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-raised px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
      FROZEN BASELINE (as of {formatDateShortCT(envelope.data_as_of)}, computation {shortSha})
    </span>
  );
}

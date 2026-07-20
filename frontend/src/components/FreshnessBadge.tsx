// UI v2. Shown on every screen (architecture §2/§6) so the dashboard never
// implies the FROZEN research baseline reflects "now." Reads provenance
// exclusively from the response envelope's own fields - never infers
// LIVE-vs-FROZEN, a date, or a version from which endpoint was called.
// `envelope.code_version` is always `source_computation_version`, never
// `snapshot_exporter_version` - enforced by the backend (atlas/api/v1/
// research.py's `_http_envelope`), not re-derived here.

import { ResponseEnvelope } from "@/lib/apiEnvelope";
import { formatClock, formatDateShort } from "@/lib/format";

export function FreshnessBadge({ envelope }: { envelope: ResponseEnvelope }) {
  if (envelope.source_track === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-open/30 bg-open/15 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-open">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-open" />
        LIVE · as of {formatClock(envelope.data_as_of)}
      </span>
    );
  }

  const shortSha = envelope.code_version ? envelope.code_version.slice(0, 7) : "unknown";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-raised px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
      FROZEN BASELINE (as of {formatDateShort(envelope.data_as_of)}, computation {shortSha})
    </span>
  );
}

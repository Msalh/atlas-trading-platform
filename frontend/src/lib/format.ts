export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatPoints(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPnl(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(digits)}%`;
}

export function formatRatio(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "-";
  return value.toFixed(digits);
}

export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// UI v2, production-hardening amendment 4. Every market timestamp in UI v2
// (Market View, Active Setup Bundle, Timeline, Episode Inspector,
// FreshnessBadge, Research Overview, Dataset Health) renders in
// America/Chicago explicitly, via these two formatters - never the
// viewer's own browser locale/timezone, which is what formatClock/
// formatDateShort above still use and continue to be used by pre-UI-v2
// pages (deliberately untouched - see those pages' own disclosed
// inconsistency notes).
//
// The IANA zone name "America/Chicago" - not a fixed UTC offset - is
// what makes daylight-saving handling automatic: the JS runtime's own
// bundled ICU timezone database applies the correct CST (UTC-6) or CDT
// (UTC-5) offset for the given instant, with no manual DST arithmetic
// and no new dependency. Both formatters append an explicit "CT" label
// themselves so no call site can render a CT timestamp without it.
//
// Locale is pinned to "en-US" here (unlike formatClock/formatDateShort's
// `undefined`, which defers to the viewer's own OS locale) - a shared
// operational timestamp meant to be unambiguous across every operator's
// screen shouldn't also vary in month/day ordering by each viewer's OS
// locale settings, and a fixed locale is what makes this formatter's
// output deterministic and testable in the first place.
export const CT_TIME_ZONE = "America/Chicago";
const CT_LOCALE = "en-US";

export function formatClockCT(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const formatted = d.toLocaleString(CT_LOCALE, {
    timeZone: CT_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return `${formatted} CT`;
}

export function formatDateShortCT(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const formatted = d.toLocaleDateString(CT_LOCALE, { timeZone: CT_TIME_ZONE, month: "short", day: "numeric" });
  return `${formatted} CT`;
}

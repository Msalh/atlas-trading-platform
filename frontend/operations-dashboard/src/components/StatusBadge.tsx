export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone = ["healthy", "ready", "current", "available", "open", "true"].includes(normalized)
    ? "tone-healthy"
    : ["degraded", "delayed", "stale", "false"].includes(normalized)
      ? "tone-degraded"
      : "tone-unavailable";
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wider ${tone}`}
    >
      {value}
    </span>
  );
}

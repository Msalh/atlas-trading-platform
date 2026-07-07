const STYLES: Record<string, string> = {
  open: "bg-open/15 text-open border-open/30",
  won: "bg-long/15 text-long border-long/30",
  lost: "bg-short/15 text-short border-short/30",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STYLES[status] ?? "bg-muted/15 text-muted border-muted/30";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${style}`}
    >
      {status}
    </span>
  );
}

export function DirectionBadge({ direction }: { direction: string | null }) {
  if (!direction) return null;
  const color = direction === "long" ? "text-long" : "text-short";
  return <span className={`font-semibold uppercase ${color}`}>{direction}</span>;
}

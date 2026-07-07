export function RiskProgressBar({ usedPct, breached }: { usedPct: number; breached: boolean }) {
  const clamped = Math.max(0, Math.min(100, usedPct));
  const color = breached ? "bg-danger" : clamped >= 75 ? "bg-warn" : "bg-ok";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-raised">
      <div className={`h-full ${color}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

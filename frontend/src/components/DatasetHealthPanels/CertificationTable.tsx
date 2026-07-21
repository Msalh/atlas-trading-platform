// UI v2, architecture §3.6. Renders scripts/certify_historical_dataset.py's
// PASS/WARNING/FAIL checks exactly as certified - a data-quality
// certification outcome, not a trading signal, so color-coding by verdict
// here does not conflict with the "no bullish/bearish language" rule (that
// rule governs market-fact display, e.g. RuleEngineViewer's FactValue).

import { CertificationCheckResult, CertificationSummary } from "@/lib/researchApi";

const CHECK_VERDICT_STYLE: Record<string, string> = {
  PASS: "text-ok",
  WARNING: "text-warn",
  FAIL: "text-danger",
};

const OVERALL_VERDICT_STYLE: Record<string, string> = {
  certified: "border-ok/40 bg-ok/10 text-ok",
  certified_with_warnings: "border-warn/40 bg-warn/10 text-warn",
  rejected: "border-danger/40 bg-danger/10 text-danger",
};

function CheckRow({ check }: { check: CertificationCheckResult }) {
  const style = CHECK_VERDICT_STYLE[check.verdict] ?? "text-muted";
  return (
    <li className="rounded-md border border-border bg-surface px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-foreground">{check.check}</span>
        <span className={`text-xs font-semibold uppercase tracking-wide ${style}`}>{check.verdict}</span>
      </div>
      <div className="mt-1 text-[11px] text-muted">{check.section}</div>
      <p className="mt-1 text-xs text-muted">{check.detail}</p>
    </li>
  );
}

export function CertificationTable({ certification }: { certification: CertificationSummary }) {
  const overallStyle = OVERALL_VERDICT_STYLE[certification.verdict] ?? "border-border bg-surface-raised text-muted";
  const bySection = new Map<string, CertificationCheckResult[]>();
  for (const check of certification.checks) {
    const existing = bySection.get(check.section) ?? [];
    existing.push(check);
    bySection.set(check.section, existing);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${overallStyle}`}>
          {certification.verdict.replace(/_/g, " ")}
        </span>
        <span className="text-xs text-muted">
          {certification.checks_run} checks · {certification.pass_count} pass · {certification.warning_count} warning ·{" "}
          {certification.fail_count} fail
        </span>
      </div>

      {Array.from(bySection.entries()).map(([section, checks]) => (
        <details key={section} className="rounded-lg border border-border bg-surface p-4" open>
          <summary className="cursor-pointer select-none text-sm font-semibold text-muted">{section}</summary>
          <ul className="mt-2 space-y-2">
            {checks.map((check, i) => (
              <CheckRow key={`${section}-${i}`} check={check} />
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}

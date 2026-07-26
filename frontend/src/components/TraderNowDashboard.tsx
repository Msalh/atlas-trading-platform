"use client";

import { useQuery } from "@tanstack/react-query";
import { StatusBadge } from "@/components/StatusBadge";
import { ApiFetchError, fetchTraderNow, type Availability, type TraderNowResponse } from "@/lib/traderNowApi";

const displayTime = (value: string | null) => {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : parsed.toLocaleString();
};
const join = (values: readonly string[]) => values.length ? values.join(", ") : "None";

function Section({ title, authority, children }: { title: string; authority: string; children: React.ReactNode }) {
  const id = `section-${title.toLowerCase().replaceAll(" ", "-")}`;
  return <section className="rounded-lg border border-border bg-surface p-4" aria-labelledby={id}>
    <header className="mb-4 border-b border-border pb-3">
      <h2 id={id} className="font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-muted">{authority}</p>
    </header>
    {children}
  </section>;
}
function Grid({ children }: { children: React.ReactNode }) {
  return <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</dl>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="min-w-0"><dt className="text-xs font-medium uppercase tracking-wide text-foreground/70">{label}</dt>
    <dd className="mt-1 break-words text-sm">{children}</dd></div>;
}
function AvailabilityView({ value }: { value: Availability }) {
  return <div className="flex flex-wrap items-center gap-2"><StatusBadge status={value.status} />
    {value.reason_codes.length > 0 && <span className="text-xs text-muted">{join(value.reason_codes)}</span>}</div>;
}

function OperationalSummary({ value }: { value: TraderNowResponse }) {
  const strategy = value.strategy.decisions[0] ?? null;
  return <section className="rounded-lg border border-open/30 bg-open/5 p-4" aria-labelledby="operational-summary">
    <header className="mb-3">
      <h2 id="operational-summary" className="font-semibold">Operational summary</h2>
      <p className="mt-1 text-xs text-foreground/70">Read-only summary of Strategy, Risk, and Decision; detailed authority sections remain below.</p>
    </header>
    <div className="grid gap-3 md:grid-cols-3">
      <div className="min-w-0 rounded border border-border bg-surface p-3">
        <h3 className="text-xs font-medium uppercase tracking-wide text-foreground/70">Strategy summary</h3>
        {strategy ? <><StatusBadge status={strategy.disposition} />
          <p className="mt-2 text-xs text-muted">Deterministic opportunity evaluation only; never an entry recommendation.</p></> :
          <p className="mt-2 text-sm text-muted">No Strategy decision is available.</p>}
      </div>
      <div className="min-w-0 rounded border border-border bg-surface p-3">
        <h3 className="text-xs font-medium uppercase tracking-wide text-foreground/70">Risk summary</h3>
        {value.risk ? <><StatusBadge status={value.risk.status} />
          <p className="mt-2 text-xs text-muted">Explicit RiskAssessment projection.</p></> :
          <><StatusBadge status="unavailable" /><p className="mt-2 text-xs text-muted">Risk is absent; no risk state has been inferred.</p></>}
      </div>
      <div className="min-w-0 rounded border border-border bg-surface p-3">
        <h3 className="text-xs font-medium uppercase tracking-wide text-foreground/70">Decision summary</h3>
        <StatusBadge status={value.decision.availability} />
        <p className="mt-2 text-xs text-muted">{value.decision.availability === "not_implemented"
          ? "Decision Engine not implemented. No WAIT, PREPARE, ENTER, or execution instruction exists."
          : value.decision.state ?? "No Decision Engine state exists."}</p>
      </div>
    </div>
  </section>;
}

function Analysis({ value }: { value: TraderNowResponse }) {
  const stale = value.source_trust?.freshness.status === "stale";
  return <div className="space-y-4">
    {stale && <div role="status" className="rounded border border-warn/40 bg-warn/10 p-3 text-sm text-warn">
      Market data is stale. Displayed analysis is not current.
    </div>}
    <OperationalSummary value={value} />
    <Section title="Market" authority="Canonical market identity and latest validated input">
      <Grid>
        <Field label="Economic product">{value.market.economic_instrument?.symbol ?? value.identity.product}</Field>
        <Field label="Source series">{value.market.market_data_series ? `${value.market.market_data_series.provider}:${value.market.market_data_series.symbol}` : "Unavailable"}</Field>
        <Field label="Series type">{value.market.market_data_series?.series_type ?? "Unavailable"}</Field>
        <Field label="Timeframe">{value.identity.timeframe}</Field>
        <Field label="Evaluation">{displayTime(value.evaluated_at)}</Field>
        <Field label="Latest closed bar">{displayTime(value.market.latest_closed_at)}</Field>
        <Field label="Bars available">{value.market.bar_count}</Field>
        <Field label="Latest close">{value.market.latest_bar?.close.value ?? "Unavailable"}</Field>
        <Field label="Listed instrument">{value.market.listed_instrument?.contract_symbol ?? "Unresolved"}</Field>
      </Grid>
    </Section>
    <Section title="Trust and availability" authority="Freshness, trust, and explicit per-stage availability">
      <Grid>
        <Field label="Overall trust"><StatusBadge status={value.trust.status} /></Field>
        <Field label="Freshness"><StatusBadge status={value.source_trust?.freshness.status ?? "unavailable"} /></Field>
        <Field label="Lateness">{value.source_trust?.freshness.lateness_seconds == null ? "Unavailable" : `${value.source_trust.freshness.lateness_seconds}s`}</Field>
        {Object.entries(value.availability).map(([name, state]) =>
          <Field key={name} label={name}><AvailabilityView value={state} /></Field>)}
      </Grid>
    </Section>
    <Section title="Facts" authority="Rule Engine facts; observations, not recommendations">
      {value.rules.facts.length === 0 ? <p className="text-sm text-muted">No Rule Engine facts are available.</p> :
        <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-xs uppercase text-muted"><tr><th className="pb-2">Fact</th><th>Status</th><th>Value</th><th>Reason</th></tr></thead>
          <tbody>{value.rules.facts.map((fact) => <tr key={fact.fact_id} className="border-t border-border">
            <td className="py-2 font-mono">{fact.fact_id}</td><td>{fact.status}</td>
            <td>{fact.value === null ? "Unavailable" : String(fact.value)}</td><td>{fact.reason ?? "—"}</td>
          </tr>)}</tbody>
        </table></div>}
    </Section>
    <div className="grid gap-4 xl:grid-cols-2">
      <Section title="Setups" authority="Detected Setup Engine outcomes">
        {value.setups.setups.length === 0 ? <p className="text-sm text-muted">No setups detected.</p> :
          <ul className="space-y-3">{value.setups.setups.map((setup) => <li key={setup.setup_id} className="rounded border border-border p-3">
            <div className="flex justify-between gap-3"><span className="font-mono text-sm">{setup.setup_id}</span><StatusBadge status={setup.status} /></div>
            <p className="mt-2 text-xs text-muted">Detected: {setup.detected === null ? "Unavailable" : String(setup.detected)} · Severity: {setup.severity ?? "Unavailable"}</p>
            {setup.reason && <p className="mt-1 text-xs">{setup.reason}</p>}
          </li>)}</ul>}
      </Section>
      <Section title="Context" authority="Market Context classification">
        {!value.context.data ? <p className="text-sm text-muted">Market Context is unavailable.</p> :
          <Grid><Field label="Session phase">{value.context.data.session.phase}</Field>
            <Field label="Volatility">{value.context.data.volatility.regime}</Field>
            <Field label="Quality">{value.context.data.quality}</Field>
            <Field label="Session drift">{value.context.data.session.drift_status}</Field>
            <Field label="ATR percentile">{value.context.data.volatility.atr_percentile_rank ?? "Unavailable"}</Field></Grid>}
      </Section>
    </div>
    <Section title="Interpretation" authority="Deterministic interpretation of Setup outcomes">
      {value.interpretations.interpretations.length === 0 ? <p className="text-sm text-muted">No setup interpretations are available.</p> :
        <ul className="grid gap-3 md:grid-cols-2">{value.interpretations.interpretations.map((item) =>
          <li key={item.interpretation_fingerprint} className="rounded border border-border p-3">
            <div className="flex justify-between gap-2"><span className="font-mono text-sm">{item.setup_id}</span><span className="uppercase">{item.direction}</span></div>
            <p className="mt-2 text-xs text-muted">Reasons: {join(item.reason_codes)}</p>
          </li>)}</ul>}
    </Section>
    <Section title="Strategy" authority="Deterministic opportunity evaluation; never an entry recommendation">
      {value.strategy.decisions.length === 0 ? <p className="text-sm text-muted">No Strategy decision is available.</p> :
        <ul className="space-y-3">{value.strategy.decisions.map((item, index) =>
          <li key={`${item.occurred_at}-${index}`} className="rounded border border-border p-3">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2"><span className="min-w-0 break-all font-mono text-sm">{item.strategy_id}@{item.strategy_version}</span><StatusBadge status={item.disposition} /></div>
            <Grid><Field label="Disposition">{item.disposition}</Field><Field label="Direction">{item.direction}</Field>
              <Field label="Confidence">{item.confidence ?? "Unavailable"}</Field><Field label="Reason codes">{join(item.reason_codes)}</Field></Grid>
          </li>)}</ul>}
    </Section>
    <div className="grid gap-4 xl:grid-cols-2">
      <Section title="Risk" authority="RiskAssessment projection when explicitly available">
        {!value.risk ? <div className="rounded border border-warn/30 bg-warn/5 p-3"><StatusBadge status="unavailable" />
          <p className="mt-2 text-sm text-muted">Risk was not supplied by the live TraderNow composition. No risk state has been inferred.</p></div> :
          <Grid><Field label="Status"><StatusBadge status={value.risk.status} /></Field>
            <Field label="Primary reason">{value.risk.primary_reason ?? "None"}</Field>
            <Field label="Approved quantity">{value.risk.approved_quantity ?? "Unavailable"}</Field>
            <Field label="Delayed data">{String(value.risk.has_delayed_data)}</Field></Grid>}
      </Section>
      <Section title="Decision" authority="Authoritative Decision Engine state exactly as returned by TraderNow">
        <StatusBadge status={value.decision.availability} />
        <p className="mt-3 text-sm">{value.decision.state ?? "No Decision Engine state exists."}</p>
        {value.decision.availability === "not_implemented" && <p className="mt-2 text-xs text-muted">
          Decision Engine not implemented. Strategy dispositions are not WAIT, PREPARE, ENTER, or execution instructions.
        </p>}
      </Section>
    </div>
  </div>;
}

function Failure({ error, retry }: { error: Error; retry: () => void }) {
  const kind = error instanceof ApiFetchError ? error.kind : "network_error";
  const failure = kind === "unauthorized"
    ? { title: "Authentication required", message: "TraderNow authentication failed. No analysis is available." }
    : kind === "forbidden"
      ? { title: "Access denied", message: "This session is not authorized to access TraderNow analysis." }
      : kind === "invalid_response"
        ? { title: "Invalid analysis response", message: "TraderNow returned a malformed or contract-invalid response. Nothing has been inferred." }
        : { title: "Live analysis unavailable", message: "TraderNow is currently unavailable. No analysis has been inferred." };
  return <div role="alert" className="rounded border border-danger/40 bg-danger/10 p-5">
    <h2 className="font-semibold">{failure.title}</h2><p className="mt-2 text-sm text-foreground/75">{failure.message}</p>
    <button onClick={retry} className="mt-4 rounded border border-border px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-open">Retry</button>
  </div>;
}

export function TraderNowDashboard() {
  const query = useQuery({ queryKey: ["trader-now", "MNQ", "5m", "displacement_volume_context"],
    queryFn: fetchTraderNow, retry: false, refetchInterval: 10_000 });
  const identitySummary = query.data
    ? `Economic product ${query.data.market.economic_instrument?.symbol ?? query.data.identity.product} · ${
      query.data.market.market_data_series
        ? `Source series ${query.data.market.market_data_series.provider}:${query.data.market.market_data_series.symbol}`
        : "Source series unavailable"
    } · ${query.data.identity.timeframe}`
    : "Canonical TraderNow composition";
  return <section className="space-y-5">
    <header className="flex min-w-0 flex-col justify-between gap-3 border-b border-border pb-4 sm:flex-row sm:items-end">
      <div><p className="text-xs uppercase tracking-[0.18em] text-muted">Live · Read only</p>
        <h1 className="mt-1 text-2xl font-semibold">Unified Market Analysis</h1>
        <p className="mt-1 break-words text-sm text-foreground/70">{identitySummary}</p></div>
      <button onClick={() => void query.refetch()} disabled={query.isFetching}
        className="rounded border border-border px-3 py-2 text-sm disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-open">
        {query.isFetching ? "Refreshing…" : "Refresh"}</button>
    </header>
    {query.isPending && <div role="status" className="rounded border border-border bg-surface p-5">Loading live TraderNow analysis…</div>}
    {query.error && <Failure error={query.error} retry={() => void query.refetch()} />}
    {query.data && <Analysis value={query.data} />}
  </section>;
}

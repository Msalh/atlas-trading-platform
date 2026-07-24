"use client";

import { Card, Field } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { useOperationsPolling } from "@/lib/polling";

function fmtTimestamp(value: string | null | undefined) {
  return value ?? "Unavailable";
}

function fmtDuration(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${value.toFixed(1)} ms`;
}

function fmtUptime(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

export function OperationsDashboard() {
  const { data, lastRefresh, state, stale } = useOperationsPolling();
  if (!data) {
    return (
      <main className="mx-auto min-h-screen max-w-7xl p-4 sm:p-6">
        <h1 className="text-xl font-semibold">TraderNow Operations</h1>
        <p className="mt-3 text-sm text-[var(--muted)]">
          {state === "auth-failed" ? "Upstream authentication failed. Polling stopped." : "Service data unavailable."}
        </p>
        <StatusBadge value={state === "auth-failed" ? "Unavailable" : "Loading"} />
      </main>
    );
  }

  const { latest, operations } = data;
  const decision = latest.strategy.decisions[0];
  const interpretation = latest.interpretations.interpretations[0];
  const trueRules = latest.rules.facts
    .filter((fact) => fact.value === true)
    .map((fact) => fact.fact_id);
  const reasonCodes = decision?.reason_codes ?? interpretation?.reason_codes ?? [];
  const overall = data.health.ok && data.readiness.ok && operations.database.ready
    ? "Healthy"
    : data.health.ok ? "Degraded" : "Unavailable";

  return (
    <main className="mx-auto min-h-screen max-w-7xl p-4 sm:p-6">
      <header className="mb-6 flex flex-col justify-between gap-3 border-b border-[var(--border)] pb-5 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Internal · Read only</p>
          <h1 className="mt-1 text-2xl font-semibold">TraderNow Operations</h1>
        </div>
        <div className="flex items-center gap-3">
          {stale && <StatusBadge value="Stale" />}
          <StatusBadge value={overall} />
        </div>
      </header>

      <section className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card title="Overall status">
          <Field label="State"><StatusBadge value={overall} /></Field>
          <Field label="Last refresh" mono>{lastRefresh?.toISOString() ?? "Unavailable"}</Field>
          <Field label="Polling">{state}</Field>
          <Field label="Retained data">{stale ? "Stale" : "Current"}</Field>
        </Card>
        <Card title="Service">
          <Field label="Liveness">{data.health.ok ? "Live" : "Unavailable"}</Field>
          <Field label="Readiness">{data.readiness.ok ? "Ready" : "Unavailable"}</Field>
          <Field label="Uptime">{fmtUptime(operations.service.uptime_seconds)}</Field>
          <Field label="Release" mono>{operations.build.release_tag}</Field>
          <Field label="Commit" mono>{operations.build.commit.slice(0, 8)}</Field>
        </Card>
        <Card title="Database">
          <Field label="Ready">{String(operations.database.ready)}</Field>
          <Field label="Transaction read only">{String(operations.database.transaction_read_only)}</Field>
          <Field label="Pool">{operations.database.pool_status}</Field>
          <Field label="Probe">{fmtDuration(operations.database.latest_probe_duration_ms)}</Field>
        </Card>
        <Card title="Request">
          <Field label="Latest duration">{fmtDuration(operations.requests.last_response_duration_ms)}</Field>
          <Field label="Latest success" mono>{fmtTimestamp(operations.requests.last_success_at)}</Field>
          <Field label="Correlation ID" mono>{data.correlationId ?? "Unavailable"}</Field>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Market data">
          <Field label="Economic instrument" mono>{latest.market.economic_instrument?.symbol}</Field>
          <Field label="Provider" mono>{latest.market.market_data_series?.provider}</Field>
          <Field label="Series symbol" mono>{latest.market.market_data_series?.symbol}</Field>
          <Field label="Series type">{latest.market.market_data_series?.series_type}</Field>
          <Field label="Latest closed bar" mono>{fmtTimestamp(latest.market.latest_closed_at)}</Field>
          <Field label="Bars in window">{latest.market.bar_count}</Field>
          <Field label="Freshness">{latest.source_trust?.freshness.status ?? "Unavailable"}</Field>
          <Field label="Lateness">{latest.source_trust?.freshness.lateness_seconds == null ? "Unavailable" : `${latest.source_trust.freshness.lateness_seconds}s`}</Field>
          <Field label="Availability">{latest.market.availability.status}</Field>
        </Card>
        <Card title="Latest analysis">
          <Field label="Evaluation" mono>{fmtTimestamp(latest.evaluated_at)}</Field>
          <Field label="Strategy" mono>{decision ? `${decision.strategy_id}@${decision.strategy_version}` : `${latest.identity.strategy_id}@${latest.identity.strategy_version}`}</Field>
          <Field label="Interpretation">{interpretation ? `${interpretation.setup_id} · ${interpretation.direction}` : "Unavailable"}</Field>
          <Field label="Triggered true rules" mono>{trueRules.length ? trueRules.join(", ") : "None"}</Field>
          <Field label="Reason codes" mono>{reasonCodes.length ? reasonCodes.join(", ") : "None"}</Field>
          <Field label="Confidence">{decision?.confidence == null ? "Unavailable" : decision.confidence}</Field>
          <Field label="Correlation ID" mono>{data.correlationId ?? "Unavailable"}</Field>
        </Card>
      </section>
    </main>
  );
}

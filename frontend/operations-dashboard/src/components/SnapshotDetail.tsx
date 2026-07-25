"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useSnapshotDetail } from "@/features/evidence/useSnapshotDetail";

function timestamp(value: string | null): string {
  if (value === null) return "Unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString();
}

function safeError(code: string): { title: string; message: string } {
  switch (code) {
    case "snapshot_not_found":
      return {
        title: "Snapshot not found",
        message: "The requested snapshot is not available.",
      };
    case "dashboard_authentication_required":
      return {
        title: "Authentication required",
        message: "Dashboard authentication is required.",
      };
    case "snapshot_upstream_authentication_failed":
      return {
        title: "Reader authentication failed",
        message: "The private reader could not authenticate.",
      };
    case "snapshot_access_forbidden":
    case "snapshot_upstream_authorization_failed":
      return {
        title: "Access denied",
        message: "The reader is not authorized to access this snapshot.",
      };
    case "snapshot_integrity_failed":
      return {
        title: "Snapshot unavailable",
        message:
          "The snapshot could not be displayed because an integrity-related failure was reported.",
      };
    case "unsupported_snapshot_schema":
      return {
        title: "Unsupported snapshot schema",
        message: "This snapshot version is not supported by the Evidence Browser.",
      };
    case "unexpected_snapshot_response":
      return {
        title: "Unexpected response",
        message: "The snapshot service returned an unexpected response.",
      };
    default:
      return {
        title: "Snapshot unavailable",
        message: "The snapshot detail is temporarily unavailable.",
      };
  }
}

export function SnapshotDetail({ snapshotId }: { snapshotId: string }) {
  const state = useSnapshotDetail(snapshotId);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, [snapshotId]);

  const error = state.status === "error" ? safeError(state.code) : null;

  return (
    <main className="mx-auto min-h-screen max-w-7xl p-4 sm:p-6">
      <Link
        className="inline-flex rounded border border-[var(--border)] px-3 py-2 text-sm font-medium"
        href="/evidence"
        prefetch={false}
      >
        Back to Evidence
      </Link>
      <header className="my-6 border-b border-[var(--border)] pb-5">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          Internal · Read only
        </p>
        <h1
          className="mt-1 text-2xl font-semibold outline-none"
          ref={heading}
          tabIndex={-1}
        >
          Snapshot Detail
        </h1>
        <p className="mt-2 break-all font-mono text-xs text-[var(--muted)]">
          {snapshotId}
        </p>
      </header>

      {state.status === "loading" && (
        <div
          className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--muted)]"
          role="status"
        >
          Loading snapshot header and indexed metadata…
        </div>
      )}

      {error && (
        <section
          aria-labelledby="snapshot-error-title"
          className="rounded-lg border border-[var(--degraded)] bg-[var(--surface)] p-6"
          role="alert"
        >
          <h2 id="snapshot-error-title" className="font-semibold">
            {error.title}
          </h2>
          <p className="mt-2 text-sm text-[var(--muted)]">{error.message}</p>
        </section>
      )}

      {state.status === "ready" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section
            aria-labelledby="detail-header-title"
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
          >
            <h2
              id="detail-header-title"
              className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]"
            >
              Snapshot header
            </h2>
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs text-[var(--muted)]">Snapshot ID</dt>
                <dd className="mt-1 break-all font-mono text-sm">
                  {state.header.snapshotId}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--muted)]">Captured</dt>
                <dd className="mt-1 text-sm">
                  <time dateTime={state.metadata.created_at}>
                    {timestamp(state.metadata.created_at)}
                  </time>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--muted)]">
                  Source identity
                </dt>
                <dd className="mt-1 break-all font-mono text-sm">
                  {state.metadata.market_data_provider ?? "Unavailable"}:
                  {state.metadata.market_data_series_symbol ?? "Unavailable"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--muted)]">
                  Snapshot schema
                </dt>
                <dd className="mt-1 font-mono text-sm">
                  {state.header.snapshotSchemaVersion}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-[var(--muted)]">
                  Evidence digest
                </dt>
                <dd className="mt-1 break-all font-mono text-sm">
                  {state.metadata.evidence_digest}
                </dd>
              </div>
            </dl>
          </section>

          <section
            aria-labelledby="indexed-metadata-title"
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
          >
            <h2
              id="indexed-metadata-title"
              className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]"
            >
              Indexed metadata
            </h2>
            <div className="mt-3 rounded border border-[var(--border)] bg-[var(--raised)] p-3 text-sm text-[var(--muted)]">
              <p>Indexed metadata is for lookup and display.</p>
              <p className="mt-2">
                Indexed metadata is non-authoritative. Evidence authority
                remains governed by the frozen Phase 17 snapshot contract.
              </p>
              <p className="mt-2">
                A metadata disagreement is never silently normalized or
                corrected by this interface.
              </p>
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              <Metadata label="Economic instrument">
                {state.metadata.economic_instrument ?? "Unavailable"}
              </Metadata>
              <Metadata label="Provider">
                {state.metadata.market_data_provider ?? "Unavailable"}
              </Metadata>
              <Metadata label="Series symbol">
                {state.metadata.market_data_series_symbol ?? "Unavailable"}
              </Metadata>
              <Metadata label="Series type">
                {state.metadata.market_data_series_type ?? "Unavailable"}
              </Metadata>
              <Metadata label="Timeframe">{state.metadata.timeframe}</Metadata>
              <Metadata label="Trust">{state.metadata.trust_status}</Metadata>
              <Metadata label="Strategy">
                {state.metadata.strategy_id}
              </Metadata>
              <Metadata label="Strategy version">
                {state.metadata.strategy_version}
              </Metadata>
              <Metadata label="Evaluated">
                {timestamp(state.metadata.evaluated_at)}
              </Metadata>
              <Metadata label="Latest closed">
                {timestamp(state.metadata.latest_closed_at)}
              </Metadata>
              <Metadata label="Supersedes">
                {state.metadata.supersedes_snapshot_id ?? "None"}
              </Metadata>
            </dl>
          </section>
        </div>
      )}
    </main>
  );
}

function Metadata({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs text-[var(--muted)]">{label}</dt>
      <dd className="mt-1 break-all text-sm">{children}</dd>
    </div>
  );
}

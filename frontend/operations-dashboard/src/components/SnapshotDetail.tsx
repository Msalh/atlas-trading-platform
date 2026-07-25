"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { SemanticEvidence } from "@/components/SemanticEvidence";
import { SemanticJson } from "@/components/SemanticJson";
import {
  useSnapshotDetail,
  type IntegrityFailureState,
} from "@/features/evidence/useSnapshotDetail";

function timestamp(value: string | null): string {
  if (value === null) return "Unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString();
}

function integrityError(
  state: IntegrityFailureState,
): { title: string; message: string } {
  switch (state) {
    case "not_found":
      return {
        title: "Snapshot not found",
        message: "The requested snapshot is not available.",
      };
    case "unauthorized":
      return {
        title: "Authentication required",
        message: "Dashboard authentication is required.",
      };
    case "forbidden":
      return {
        title: "Access denied",
        message: "The reader is not authorized to access this snapshot.",
      };
    case "failed":
      return {
        title: "Integrity verification failed",
        message: "The Snapshot API did not verify this snapshot evidence.",
      };
    case "metadata_disagreement":
      return {
        title: "Indexed metadata disagreement",
        message: "Indexed metadata does not agree with verified evidence.",
      };
    case "unsupported_schema":
      return {
        title: "Unsupported snapshot schema",
        message: "This snapshot version is not supported by the Evidence Browser.",
      };
    case "malformed_response":
      return {
        title: "Malformed verification response",
        message:
          "The Snapshot API returned invalid data required for integrity gating.",
      };
    case "timeout":
      return {
        title: "Integrity verification timed out",
        message: "The integrity result was not available before the timeout.",
      };
    case "unavailable":
      return {
        title: "Integrity verification unavailable",
        message: "The integrity service is temporarily unavailable.",
      };
  }
}

export function SnapshotDetail({ snapshotId }: { snapshotId: string }) {
  const { state, refresh } = useSnapshotDetail(snapshotId);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, [snapshotId]);

  const error =
    state.status === "integrity_error"
      ? integrityError(state.integrityState)
      : null;

  return (
    <main className="mx-auto min-h-screen max-w-7xl p-4 sm:p-6">
      <header className="mb-4 border-b border-[var(--border)] pb-5">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          Internal · Read only
        </p>
        <h1
          className="mt-1 text-2xl font-semibold focus:outline focus:outline-2 focus:outline-offset-4 focus:outline-[var(--healthy)]"
          ref={heading}
          tabIndex={-1}
        >
          Snapshot Detail
        </h1>
        <p className="mt-2 break-all font-mono text-xs text-[var(--muted)]">
          {snapshotId}
        </p>
      </header>
      <Link
        className="mb-6 inline-flex rounded border border-[var(--border)] px-3 py-2 text-sm font-medium focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[var(--healthy)]"
        href="/evidence"
        prefetch={false}
      >
        Back to Evidence
      </Link>

      {state.status === "integrity_loading" && (
        <div
          className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--muted)]"
          role="status"
        >
          Verifying snapshot integrity…
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
          <p className="mt-2 break-words text-sm text-[var(--muted)]">
            {error.message}
          </p>
          <button
            className="mt-4 rounded border border-[var(--border)] px-3 py-2 text-sm font-medium focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[var(--healthy)]"
            onClick={refresh}
            type="button"
          >
            Retry integrity verification
          </button>
        </section>
      )}

      {state.status === "verified" && (
        <>
          <section
            aria-labelledby="integrity-verified-title"
            className="mb-4 rounded-lg border border-[var(--healthy)] bg-[var(--surface)] p-4"
          >
            <h2 id="integrity-verified-title" className="font-semibold">
              Verified canonical evidence
            </h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Evidence digest verified by the Snapshot API.
            </p>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Indexed metadata agrees with verified evidence.
            </p>
            <button
              className="mt-3 rounded border border-[var(--border)] px-3 py-2 text-sm font-medium focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[var(--healthy)]"
              onClick={refresh}
              type="button"
            >
              Refresh integrity and evidence
            </button>
          </section>
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
                  <dt className="text-xs text-[var(--muted)]">
                    Snapshot schema
                  </dt>
                  <dd className="mt-1 font-mono text-sm">
                    {state.header.snapshotSchemaVersion}
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
                <Metadata label="Captured">
                  {timestamp(state.metadata.created_at)}
                </Metadata>
                <Metadata label="Evidence digest">
                  <span className="font-mono">
                    {state.metadata.evidence_digest}
                  </span>
                </Metadata>
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
          <SemanticEvidence evidence={state.semanticEvidence} />
          <SemanticJson formattedJson={state.formattedJson} />
        </>
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

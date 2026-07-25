"use client";

import Link from "next/link";
import { useEvidenceList } from "@/features/evidence/useEvidenceList";

function formatTimestamp(value: string | null): string {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString();
}

function errorMessage(code: string): string {
  switch (code) {
    case "dashboard_authentication_required":
      return "Dashboard authentication is required.";
    case "snapshot_rate_limited":
      return "Evidence requests are temporarily rate limited. Try again shortly.";
    case "evidence_browser_disabled":
      return "The Evidence Browser is disabled.";
    case "invalid_snapshot_request":
      return "The evidence list request was rejected.";
    case "unexpected_evidence_response":
    case "unexpected_snapshot_response":
      return "The evidence service returned an unsupported response.";
    default:
      return "The evidence list is temporarily unavailable.";
  }
}

export function EvidenceList() {
  const controller = useEvidenceList();
  const { state } = controller;

  return (
    <main className="mx-auto min-h-screen max-w-7xl p-4 sm:p-6">
      <header className="mb-6 border-b border-[var(--border)] pb-5">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          Internal · Read only
        </p>
        <h1 className="mt-1 text-2xl font-semibold">Snapshot Evidence</h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--muted)]">
          Immutable analysis snapshots available through the private reader
          boundary. Indexed fields shown here are non-authoritative metadata.
        </p>
      </header>

      <section
        aria-labelledby="snapshot-list-heading"
        aria-busy={state.status === "loading"}
      >
        <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <h2 id="snapshot-list-heading" className="text-lg font-semibold">
              Snapshots
            </h2>
            <p className="mt-1 text-sm text-[var(--muted)]" aria-live="polite">
              Page {controller.pageNumber}
              {state.status === "loading" ? " · Loading" : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="grid gap-1 text-xs text-[var(--muted)]">
              Page size
              <select
                aria-label="Page size"
                className="rounded border border-[var(--border)] bg-[var(--raised)] px-3 py-2 text-sm text-[var(--text)]"
                onChange={(event) =>
                  controller.changePageSize(Number(event.target.value))
                }
                value={controller.pageSize}
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
            <button
              className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!controller.hasPrevious}
              onClick={controller.previous}
              type="button"
            >
              Previous
            </button>
            <button
              className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!controller.hasNext}
              onClick={controller.next}
              type="button"
            >
              Next
            </button>
            <button
              className="rounded border border-[var(--border)] px-3 py-2 text-sm"
              onClick={controller.latest}
              type="button"
            >
              Latest
            </button>
            <button
              className="rounded border border-[var(--border)] px-3 py-2 text-sm"
              onClick={controller.refresh}
              type="button"
            >
              Refresh
            </button>
          </div>
        </div>

        {state.status === "loading" && state.items.length === 0 && (
          <div
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--muted)]"
            role="status"
          >
            Loading snapshot evidence…
          </div>
        )}

        {state.status === "empty" && (
          <div
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6"
            role="status"
          >
            <h3 className="font-semibold">No snapshots available</h3>
            <p className="mt-2 text-sm text-[var(--muted)]">
              The reader returned an empty evidence page.
            </p>
          </div>
        )}

        {state.status === "error" && (
          <div
            className="rounded-lg border border-[var(--degraded)] bg-[var(--surface)] p-6"
            role="alert"
          >
            <h3 className="font-semibold">Evidence list unavailable</h3>
            <p className="mt-2 text-sm text-[var(--muted)]">
              {errorMessage(state.code)}
            </p>
          </div>
        )}

        {state.items.length > 0 && (
          <ul className="grid list-none gap-3 p-0" aria-label="Snapshot list">
            {state.items.map((snapshot) => (
              <li key={snapshot.snapshot_id}>
                <article className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <h3 className="text-sm font-semibold">
                        {snapshot.economic_instrument ?? "Unknown instrument"}
                      </h3>
                      <p className="mt-1 break-all font-mono text-xs text-[var(--muted)]">
                        {snapshot.snapshot_id}
                      </p>
                      <Link
                        className="mt-3 inline-flex rounded border border-[var(--border)] px-3 py-2 text-sm font-medium"
                        href={`/evidence/${snapshot.snapshot_id}`}
                        prefetch={false}
                      >
                        View snapshot
                      </Link>
                    </div>
                    <dl className="grid gap-2 text-sm">
                      <div>
                        <dt className="text-xs text-[var(--muted)]">Created</dt>
                        <dd>
                          <time dateTime={snapshot.created_at}>
                            {formatTimestamp(snapshot.created_at)}
                          </time>
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[var(--muted)]">
                          Latest closed
                        </dt>
                        <dd>
                          {snapshot.latest_closed_at ? (
                            <time dateTime={snapshot.latest_closed_at}>
                              {formatTimestamp(snapshot.latest_closed_at)}
                            </time>
                          ) : (
                            "Unavailable"
                          )}
                        </dd>
                      </div>
                    </dl>
                    <dl className="grid gap-2 text-sm">
                      <div>
                        <dt className="text-xs text-[var(--muted)]">
                          Market data series
                        </dt>
                        <dd className="break-all font-mono">
                          {snapshot.market_data_provider ?? "Unknown"}:
                          {snapshot.market_data_series_symbol ?? "Unknown"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[var(--muted)]">
                          Timeframe · Strategy
                        </dt>
                        <dd>
                          {snapshot.timeframe} · {snapshot.strategy_id}
                        </dd>
                      </div>
                    </dl>
                    <dl className="grid gap-2 text-sm">
                      <div>
                        <dt className="text-xs text-[var(--muted)]">Trust</dt>
                        <dd>{snapshot.trust_status}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-[var(--muted)]">
                          Evidence digest
                        </dt>
                        <dd className="break-all font-mono text-xs">
                          {snapshot.evidence_digest}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </article>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

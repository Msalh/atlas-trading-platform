"use client";

// Sprint 10 Slice D. Snapshot Explorer + Lineage Viewer - the first deep
// inspection page. Lets an operator pick one entry from the latest
// LeaderboardSnapshot and see the complete provenance chain behind it:
// Hypothesis -> Realization -> Experiment -> Evidence -> Validation ->
// Promotion. Still strictly read-only - no editing, no Promotion actions,
// no Run Center, no navigation changes, no filtering/search/export/
// pagination (the entry selector is a single native <select> over the
// snapshot's own already-ranked entry list - there is nothing to page
// through).
//
// Reuses fetchLatestSnapshot() unchanged from Slice B/C for the snapshot
// summary and entry list - no new snapshot-fetching logic. The only new
// data call is fetchLineage(), added to researchOpsApi.ts in this slice,
// against GET /research/lineage (Slice A, already BFF-allowlisted with
// promotion_id/validation_id - no proxy change needed here).
//
// Deliberately does NOT modify LeaderboardTable.tsx to link here - adding
// a "view lineage" link would be a navigation change, out of this slice's
// scope, and Slice C is certified. This page is reachable only by direct
// URL until Slice G's own navigation work links it in.
//
// One disclosed, deliberate gap: the Hypothesis node below shows only
// hypothesis_id, never a full Hypothesis entity (statement/author/
// dataset). GET /research/lineage never returns one - not an oversight in
// this slice, but a reflection of a pre-existing, already-disclosed
// Sprint 9 finding: the real pipeline never persists Hypothesis objects to
// the Ledger's HypothesisRegistry at all. Extending the backend endpoint
// to fetch something the pipeline never writes would return null for
// every hypothesis in production today - not "absolutely necessary," so
// per the Slice D kickoff's own instruction, no backend change is
// proposed for this; the gap is simply shown as-is.
//
// Sprint 10 Slice G: SectionLoading/EmptyPanel (previously local to this
// page) are now shared - see components/ResearchOps/SectionLoading.tsx
// and EmptyPanel.tsx's own comments for why. Also adds this page's own
// NextStepLink to the Promotion Queue, the next hop in the workflow order.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyPanel } from "@/components/ResearchOps/EmptyPanel";
import { LineageChain, LineageNode } from "@/components/ResearchOps/LineageChain";
import { NextStepLink } from "@/components/ResearchOps/NextStepLink";
import { SectionLoading } from "@/components/ResearchOps/SectionLoading";
import { StatCard } from "@/components/ResearchOps/StatCard";
import { formatClockCT } from "@/lib/format";
import {
  ApiFetchError,
  LineageResponse,
  LineageVerdict,
  fetchLatestSnapshot,
  fetchLineage,
} from "@/lib/researchOpsApi";

const VERDICT_LABEL: Record<LineageVerdict, string> = {
  supported: "Supported",
  not_supported: "Not Supported",
  inconclusive: "Inconclusive",
};

const VERDICT_TONE: Record<LineageVerdict, "ok" | "warn" | "danger"> = {
  supported: "ok",
  not_supported: "danger",
  inconclusive: "warn",
};

const DECISION_LABEL: Record<string, string> = {
  approved: "Approved",
  declined: "Declined",
  deferred: "Deferred",
};

const DECISION_TONE: Record<string, "ok" | "warn" | "danger"> = {
  approved: "ok",
  declined: "danger",
  deferred: "warn",
};

function buildLineageNodes(lineage: LineageResponse): LineageNode[] {
  return [
    {
      label: "Hypothesis",
      items: [{ title: lineage.hypothesis_id, fields: [] }],
      emptyMessage: "No hypothesis on record.",
    },
    {
      label: "Realization",
      items: lineage.realization
        ? [
            {
              title: lineage.realization.realization_id,
              fields: [
                { label: "Kind", value: lineage.realization.kind },
                { label: "Version", value: lineage.realization.version },
                { label: "Created", value: formatClockCT(lineage.realization.created_at) },
              ],
              badge: { label: lineage.realization.status, tone: "neutral" },
            },
          ]
        : [],
      emptyMessage: "No realization on record for this hypothesis.",
    },
    {
      label: "Experiment",
      items: lineage.experiments.map((exp) => ({
        title: exp.experiment_id,
        fields: [
          { label: "Executed", value: formatClockCT(exp.executed_at) },
          { label: "Code Version", value: exp.code_version ?? "—" },
        ],
        badge: { label: exp.passed ? "Passed" : "Failed", tone: exp.passed ? "ok" : "danger" },
      })),
      emptyMessage: "No experiments on record.",
    },
    {
      label: "Evidence",
      items: lineage.evidence.map((ev) => ({
        title: ev.evidence_id,
        fields: [
          { label: "Computed", value: formatClockCT(ev.computed_at) },
          { label: "Metrics", value: `${Object.keys(ev.metrics).length} recorded` },
        ],
      })),
      emptyMessage: "No evidence on record.",
    },
    {
      label: "Validation",
      items: lineage.validation_results.map((v) => ({
        title: v.validation_id,
        fields: [
          { label: "Validated", value: formatClockCT(v.validated_at) },
          { label: "Out-of-Sample", value: v.out_of_sample ? "Yes" : "No" },
        ],
        badge: { label: VERDICT_LABEL[v.verdict], tone: VERDICT_TONE[v.verdict] },
      })),
      emptyMessage: "No validation result on record.",
    },
    {
      label: "Promotion",
      items: lineage.promotion_records.map((p) => ({
        title: p.promotion_id,
        fields: [
          { label: "Reviewer", value: p.reviewer },
          { label: "Decided", value: formatClockCT(p.decided_at) },
        ],
        badge: { label: DECISION_LABEL[p.decision] ?? p.decision, tone: DECISION_TONE[p.decision] ?? "neutral" },
      })),
      emptyMessage: "No promotion decision recorded yet.",
    },
  ];
}

export default function SnapshotExplorerPage() {
  const snapshotQuery = useQuery<Awaited<ReturnType<typeof fetchLatestSnapshot>>, ApiFetchError>({
    queryKey: ["research-ops-latest-snapshot"],
    queryFn: fetchLatestSnapshot,
  });

  const [selectedIndex, setSelectedIndex] = useState(0);
  const entries = snapshotQuery.data?.entries ?? [];
  const selectedEntry = entries[selectedIndex] ?? null;

  const lineageQuery = useQuery<LineageResponse, ApiFetchError>({
    queryKey: ["research-ops-lineage", selectedEntry?.validation_id ?? null],
    queryFn: () => fetchLineage({ validationId: selectedEntry!.validation_id! }),
    enabled: selectedEntry !== null && selectedEntry.validation_id !== null,
  });

  const nodes = useMemo(() => (lineageQuery.data ? buildLineageNodes(lineageQuery.data) : []), [lineageQuery.data]);

  const snapshotNotFound = snapshotQuery.isError && snapshotQuery.error.kind === "not_found";
  const snapshotDegraded = snapshotQuery.isError && !snapshotNotFound;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Snapshot Explorer</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted">Research Engine operations - read-only</span>
          <NextStepLink href="/research-ops/promotion/queue" label="Promotion Queue" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {snapshotQuery.data ? (
          <StatCard label="Snapshot ID" value={snapshotQuery.data.snapshot_id} />
        ) : snapshotNotFound ? (
          <StatCard label="Snapshot ID" value="" empty="No snapshot recorded yet." />
        ) : snapshotDegraded ? (
          <StatCard label="Snapshot ID" value="" empty={snapshotQuery.error?.message ?? "Unavailable."} />
        ) : (
          <SectionLoading title="Snapshot ID" />
        )}

        {snapshotQuery.data ? (
          <StatCard label="Snapshot Timestamp" value={formatClockCT(snapshotQuery.data.created_at)} />
        ) : snapshotNotFound || snapshotDegraded ? (
          <StatCard label="Snapshot Timestamp" value="" empty="Unavailable." />
        ) : (
          <SectionLoading title="Snapshot Timestamp" />
        )}

        {snapshotQuery.data ? (
          <StatCard label="Entry Count" value={String(snapshotQuery.data.entries.length)} />
        ) : snapshotNotFound || snapshotDegraded ? (
          <StatCard label="Entry Count" value="" empty="Unavailable." />
        ) : (
          <SectionLoading title="Entry Count" />
        )}
      </div>

      {snapshotQuery.data ? (
        entries.length === 0 ? (
          <EmptyPanel message="The latest snapshot has no ranked hypotheses." />
        ) : (
          <>
            <div className="rounded-lg border border-border bg-surface p-4">
              <label htmlFor="entry-select" className="mb-2 block text-sm font-semibold uppercase tracking-wide text-muted">
                Entry
              </label>
              <select
                id="entry-select"
                className="w-full max-w-xl rounded border border-border bg-surface-raised px-3 py-2 font-mono text-sm text-foreground"
                value={selectedIndex}
                onChange={(e) => setSelectedIndex(Number(e.target.value))}
              >
                {entries.map((entry, index) => (
                  <option key={`${entry.hypothesis_id}-${entry.realization_id ?? "none"}`} value={index}>
                    Rank {entry.rank} - {entry.hypothesis_id}
                    {entry.realization_id ? ` (${entry.realization_id})` : ""}
                  </option>
                ))}
              </select>
            </div>

            {selectedEntry && selectedEntry.validation_id === null ? (
              <EmptyPanel message="This entry has no recorded validation - lineage is unavailable." />
            ) : lineageQuery.data ? (
              <div className="space-y-3">
                {lineageQuery.data.warnings.length > 0 && (
                  <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-xs text-warn">
                    {lineageQuery.data.warnings.map((warning) => (
                      <p key={warning}>{warning}</p>
                    ))}
                  </div>
                )}
                <LineageChain nodes={nodes} />
              </div>
            ) : lineageQuery.isError ? (
              lineageQuery.error.kind === "not_found" ? (
                <EmptyPanel message="No lineage could be found for this entry's validation result." />
              ) : (
                <EmptyPanel message={lineageQuery.error.message} tone="error" />
              )
            ) : (
              <EmptyPanel message="Loading lineage…" />
            )}
          </>
        )
      ) : snapshotNotFound ? (
        <EmptyPanel message="No snapshot has been recorded yet." />
      ) : snapshotDegraded ? (
        <EmptyPanel message={snapshotQuery.error?.message ?? "Unavailable."} tone="error" />
      ) : (
        <EmptyPanel message="Loading…" />
      )}
    </section>
  );
}

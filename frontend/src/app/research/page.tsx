"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { MismatchBanner, isSymbolTimeframeMismatch } from "@/components/MismatchBanner";
import { JsonSection } from "@/components/ResearchOverviewPanels/JsonSection";
import { ApiFetchError, fetchRe1Summary, fetchRe2Summary } from "@/lib/researchApi";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export default function ResearchOverviewPage() {
  // Page-local stand-in for the shared, layout-level LIVE symbol/timeframe
  // selector (architecture §8) - that selector lands with Market View
  // (Stage 2, F5). This page has no live data of its own, but §3.5 still
  // requires its manifest-locked FROZEN identity to be checked against
  // "the live selector" - this local input lets that check run today; it
  // gets replaced by the shared selector, not duplicated alongside it, once
  // F5 ships. A disclosed, deliberately-deferred inconsistency, same
  // posture as this app's existing NEXT_PUBLIC_API_KEY note.
  const [liveSymbol, setLiveSymbol] = useState("MNQ1!");
  const [liveTimeframe, setLiveTimeframe] = useState("5m");

  const re1 = useQuery<Awaited<ReturnType<typeof fetchRe1Summary>>, ApiFetchError>({
    queryKey: ["research-re1-summary"],
    queryFn: fetchRe1Summary,
  });
  const re2 = useQuery<Awaited<ReturnType<typeof fetchRe2Summary>>, ApiFetchError>({
    queryKey: ["research-re2-summary"],
    queryFn: fetchRe2Summary,
  });

  const re1Report = re1.data && isRecord(re1.data.report) ? re1.data.report : null;
  const re2Report = re2.data && isRecord(re2.data.report) ? re2.data.report : null;

  // Both snapshots are manifest-locked to the same frozen baseline identity
  // (today always MNQ1! / 5m) - either envelope's symbol/timeframe suffices
  // for the §8 mismatch check.
  const frozenSymbol = re1.data?.envelope.symbol ?? re2.data?.envelope.symbol ?? null;
  const frozenTimeframe = re1.data?.envelope.timeframe ?? re2.data?.envelope.timeframe ?? null;
  const mismatched =
    frozenSymbol !== null &&
    frozenTimeframe !== null &&
    isSymbolTimeframeMismatch(frozenSymbol, frozenTimeframe, liveSymbol, liveTimeframe);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Research Overview</h1>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="research-live-symbol">
              Live symbol
            </label>
            <input
              id="research-live-symbol"
              value={liveSymbol}
              onChange={(e) => setLiveSymbol(e.target.value.trim())}
              className="w-28 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted" htmlFor="research-live-timeframe">
              Live timeframe
            </label>
            <input
              id="research-live-timeframe"
              value={liveTimeframe}
              onChange={(e) => setLiveTimeframe(e.target.value.trim())}
              className="w-20 rounded border border-border bg-surface-raised px-2 py-1 text-sm"
            />
          </div>
        </div>
      </div>

      {frozenSymbol && frozenTimeframe && (
        <MismatchBanner
          frozenSymbol={frozenSymbol}
          frozenTimeframe={frozenTimeframe}
          liveSymbol={liveSymbol}
          liveTimeframe={liveTimeframe}
        />
      )}

      {(re1.isError || re2.isError) && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
          {re1.error?.message ?? re2.error?.message}
        </div>
      )}

      {(re1.isLoading || re2.isLoading) && <p className="text-sm text-muted">Loading…</p>}

      {!mismatched && re1.data && <FreshnessBadge envelope={re1.data.envelope} />}

      {!mismatched && re1Report && (
        <JsonSection
          title="RE-1 Summary"
          description="Fact-level statistical profile: conditional probabilities, fact profiles, pairwise relationships, time distribution."
          data={re1Report}
        />
      )}

      {!mismatched && re2Report && (
        <>
          <JsonSection title="RE-2 Summary" description="Per-setup episode profile." data={re2Report.setup_profile} />
          <JsonSection
            title="Time Concentration"
            description="Activation time-of-day distribution per setup."
            data={re2Report.time_distribution}
          />
          <JsonSection title="Overlap Matrix" description="Simultaneous-activation overlap between setups." data={re2Report.overlap} />
          <JsonSection title="Clustering Summary" description="Episode clustering by proximity in time." data={re2Report.clustering} />
          <JsonSection title="Transition Summary" description="Setup-to-setup transition matrix and recurrence rates." data={re2Report.transitions} />
        </>
      )}
    </section>
  );
}

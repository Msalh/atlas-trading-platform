"use client";

import { useQuery } from "@tanstack/react-query";
import { FreshnessBadge } from "@/components/FreshnessBadge";
import { MismatchBanner, isSymbolTimeframeMismatch } from "@/components/MismatchBanner";
import { JsonSection } from "@/components/ResearchOverviewPanels/JsonSection";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, fetchRe1Summary, fetchRe2Summary } from "@/lib/researchApi";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export default function ResearchOverviewPage() {
  // The shared, layout-level LIVE symbol/timeframe selector (architecture
  // §8, F5) - this page has no live data of its own, but §3.5 still
  // requires its manifest-locked FROZEN identity to be checked against it.
  const { symbol: liveSymbol, timeframe: liveTimeframe } = useLiveSelector();

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
        <span className="text-xs text-muted">
          Current live selection: <span className="font-mono text-foreground">{liveSymbol}</span> /{" "}
          <span className="font-mono text-foreground">{liveTimeframe}</span>
        </span>
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

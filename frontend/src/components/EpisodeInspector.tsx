// UI v2, architecture §3.3. HYBRID - the current episode is LIVE, the
// duration distribution is FROZEN (RE-2), kept visually distinct: the live
// panel and the frozen panel are two separate cards, never merged into one
// number. On a symbol/timeframe mismatch (§8), the historical distribution
// is hidden entirely and replaced by MismatchBanner's exact copy - never a
// partial render against the wrong baseline.

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { activationText } from "@/components/ActiveSetupBundle";
import { EpisodeDurationStrip } from "@/components/EpisodeDurationStrip";
import { MismatchBanner, isSymbolTimeframeMismatch } from "@/components/MismatchBanner";
import { formatClock } from "@/lib/format";
import { useLiveSelector } from "@/lib/liveSelector";
import { ApiFetchError, ResearchSummaryResponse, fetchRe2Summary, findSetupProfileEntry } from "@/lib/researchApi";
import { LiveEpisodeProjection } from "@/lib/setupEngineApi";
import { useLiveEpisodes } from "@/lib/useLiveEpisodes";

function terminationText(ep: LiveEpisodeProjection): string {
  switch (ep.termination_reason) {
    case "became_false":
      return "Ended: the condition became false.";
    case "insufficient_data":
      return "Ended: the following bar was insufficient data.";
    case "segment_end":
      return "Ended: the data segment ended (a gap follows).";
    default:
      return "Ended.";
  }
}

function RecentEpisodeRow({ episode }: { episode: LiveEpisodeProjection }) {
  return (
    <li className="rounded-md border border-border bg-surface px-3 py-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-foreground">{episode.duration_bars_observed} bars</span>
        <span className="text-muted">{formatClock(episode.end_timestamp_observed)}</span>
      </div>
      <div className="mt-1 text-muted">{terminationText(episode)}</div>
    </li>
  );
}

export function EpisodeInspector() {
  const { symbol, timeframe } = useLiveSelector();
  const [selectedSetup, setSelectedSetup] = useState<string | null>(null);

  const live = useLiveEpisodes();
  const re2 = useQuery<ResearchSummaryResponse, ApiFetchError>({
    queryKey: ["research-re2-summary"],
    queryFn: fetchRe2Summary,
  });

  const setupNames = live.data?.found ? Object.keys(live.data.setups) : [];
  const activeSetup = (selectedSetup && setupNames.includes(selectedSetup) ? selectedSetup : setupNames[0]) ?? null;

  const snapshot = live.data?.found && activeSetup ? live.data.setups[activeSetup] : undefined;
  const currentEpisode = snapshot?.current_episode ?? null;
  const recentEpisodes = snapshot?.recent_episodes ?? [];

  const frozenSymbol = re2.data?.envelope.symbol;
  const frozenTimeframe = re2.data?.envelope.timeframe;
  const mismatched =
    frozenSymbol !== undefined &&
    frozenTimeframe !== undefined &&
    isSymbolTimeframeMismatch(frozenSymbol, frozenTimeframe, symbol, timeframe);

  const durationEntry =
    re2.data && activeSetup && !mismatched ? findSetupProfileEntry(re2.data.report, activeSetup) : null;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-surface p-4">
        <label className="text-xs text-muted" htmlFor="episode-inspector-setup">
          Setup
        </label>
        <select
          id="episode-inspector-setup"
          value={activeSetup ?? ""}
          onChange={(e) => setSelectedSetup(e.target.value)}
          disabled={setupNames.length === 0}
          className="mt-1 block rounded border border-border bg-surface-raised px-2 py-1 text-sm"
        >
          {setupNames.length === 0 && <option value="">No setups available</option>}
          {setupNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Current Episode (Live)</h2>
        {live.isError && <p className="text-sm text-danger">{live.error.message}</p>}
        {live.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {currentEpisode ? (
          <>
            <p className="text-sm text-foreground">{activationText(currentEpisode)}</p>
            <p className="mt-1 text-xs text-muted">{currentEpisode.is_continuation ? "Continuation bar" : "Activation bar"}</p>
            <p className="mt-1 text-sm text-foreground">Active through last closed bar.</p>
          </>
        ) : (
          activeSetup && !live.isLoading && <p className="text-sm text-muted">{activeSetup} is not currently active.</p>
        )}
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Historical Duration Distribution (Frozen)</h2>
        {frozenSymbol && frozenTimeframe && (
          <MismatchBanner frozenSymbol={frozenSymbol} frozenTimeframe={frozenTimeframe} liveSymbol={symbol} liveTimeframe={timeframe} />
        )}
        {!mismatched && durationEntry && (
          <EpisodeDurationStrip
            distribution={durationEntry.fully_observed_duration}
            liveDurationBars={currentEpisode?.duration_bars_observed ?? null}
          />
        )}
        {!mismatched && re2.data && activeSetup && !durationEntry && (
          <p className="text-sm text-muted">No frozen distribution available for {activeSetup}.</p>
        )}
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Recent Activation History (Live)</h2>
        {recentEpisodes.length === 0 ? (
          <p className="text-sm text-muted">No recently closed episodes in this window.</p>
        ) : (
          <ul className="space-y-2">
            {recentEpisodes.map((episode, i) => (
              <RecentEpisodeRow key={`${episode.observed_start_timestamp}-${i}`} episode={episode} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

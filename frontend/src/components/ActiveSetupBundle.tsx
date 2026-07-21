// UI v2, architecture §3.2. Every setup simultaneously active right now,
// via the shared useLiveEpisodes hook. Copy is exactly what the approved
// requirements specify:
//   - left_boundary_reason=query_window_start: "Active for at least N bars
//     — activation occurred before the loaded window."
//   - left_boundary_reason=segment_start: "Active for at least N bars —
//     activation occurred before available data begins." (architecture
//     §3.3's own second variant, reused here for the same left-boundary
//     case)
//   - observed_activation / insufficient_data (activation_timestamp_observed
//     is known): the real timestamp is shown as the activation time -
//     observed_start_timestamp itself is NEVER labeled as a confirmed
//     activation when activation_timestamp_observed is null.
//   - every card additionally reads "Active through last closed bar." -
//     current_episode is only ever populated when is_active=true (see
//     atlas/live_view/episode_projector.py's build_live_window_result), so
//     end_timestamp_observed (always null here) is never referenced.

"use client";

import { formatClockCT } from "@/lib/format";
import { LiveEpisodeProjection, LiveSetupSnapshot } from "@/lib/setupEngineApi";
import { useLiveEpisodes } from "@/lib/useLiveEpisodes";

export function activationText(ep: LiveEpisodeProjection): string {
  switch (ep.left_boundary_reason) {
    case "observed_activation":
    case "insufficient_data":
      return `Activated at ${formatClockCT(ep.activation_timestamp_observed)}`;
    case "segment_start":
      return `Active for at least ${ep.duration_bars_observed} bars — activation occurred before available data begins.`;
    case "query_window_start":
      return `Active for at least ${ep.duration_bars_observed} bars — activation occurred before the loaded window.`;
  }
}

function SetupCard({ setupName, episode }: { setupName: string; episode: LiveEpisodeProjection }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="font-mono text-sm text-foreground">{setupName}</h3>
      <p className="mt-2 text-sm text-foreground">{activationText(episode)}</p>
      <p className="mt-1 text-xs text-muted">{episode.is_continuation ? "Continuation bar" : "Activation bar"}</p>
      <p className="mt-1 text-sm text-foreground">Active through last closed bar.</p>
    </div>
  );
}

function activeEntries(setups: Record<string, LiveSetupSnapshot>): [string, LiveEpisodeProjection][] {
  const entries: [string, LiveEpisodeProjection][] = [];
  for (const [name, snapshot] of Object.entries(setups)) {
    if (snapshot.current_episode) entries.push([name, snapshot.current_episode]);
  }
  return entries;
}

export function ActiveSetupBundle() {
  const { data, error, isError, isLoading } = useLiveEpisodes();

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Active Setup Bundle</h2>
      {isError && <p className="text-sm text-danger">{error.message}</p>}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && !data.found && <p className="text-sm text-muted">No MarketState has been ingested yet.</p>}
      {data?.found && (
        <>
          {activeEntries(data.setups).length === 0 ? (
            <p className="text-sm text-muted">No setups are currently active.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {activeEntries(data.setups).map(([name, episode]) => (
                <SetupCard key={name} setupName={name} episode={episode} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

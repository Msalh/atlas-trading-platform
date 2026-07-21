// UI v2, architecture §3.4. One lane per setup, via the same shared
// useLiveEpisodes hook Active Setup Bundle uses (§9). Six required visual
// distinctions, each backed by a testable `data-*` attribute:
//   - observed activation edge (data-left-edge="observed") vs unresolved
//     left edge (data-left-edge="unresolved", segment_start/query_window_start)
//   - closed right edge (data-right-edge="closed") vs currently-open right
//     edge (data-right-edge="open", is_active=true)
//   - a segment/data gap renders as an explicit, labeled marker between
//     blocks, never a silent visual absence
//   - a simultaneous multi-label ActivationEvent renders its
//     activated_setups as one joined, alphabetically-already-sorted label -
//     never as separately ordered rows, so no ordering is implied among
//     same-bar activations

"use client";

import { formatClockCT } from "@/lib/format";
import { LiveActivationEvent, LiveEpisodeProjection } from "@/lib/setupEngineApi";
import { useLiveEpisodes } from "@/lib/useLiveEpisodes";

function isLeftUnresolved(episode: LiveEpisodeProjection): boolean {
  return episode.left_boundary_reason === "segment_start" || episode.left_boundary_reason === "query_window_start";
}

function EpisodeBlock({ episode }: { episode: LiveEpisodeProjection }) {
  const leftUnresolved = isLeftUnresolved(episode);
  const leftEdgeClass = leftUnresolved
    ? "border-l-2 border-dashed border-muted/50 opacity-70"
    : "border-l-2 border-solid border-foreground";
  const rightEdgeClass = episode.is_active
    ? "border-r-2 border-dashed border-open"
    : "border-r-2 border-solid border-foreground";

  return (
    <div
      data-left-edge={leftUnresolved ? "unresolved" : "observed"}
      data-right-edge={episode.is_active ? "open" : "closed"}
      className={`flex min-w-[92px] flex-col justify-center gap-0.5 rounded-sm border-y border-border bg-surface-raised px-2 py-2 text-[11px] ${leftEdgeClass} ${rightEdgeClass}`}
    >
      <span className="text-foreground">{episode.duration_bars_observed} bars</span>
      <span className="text-muted">{episode.is_active ? "open" : "closed"}</span>
    </div>
  );
}

function GapMarker() {
  return (
    <div data-testid="gap-marker" className="mx-1 flex items-center px-1 text-[10px] uppercase tracking-wide text-warn">
      gap
    </div>
  );
}

function SetupLane({ setupName, episodes }: { setupName: string; episodes: LiveEpisodeProjection[] }) {
  const sorted = [...episodes].sort((a, b) => a.observed_start_timestamp.localeCompare(b.observed_start_timestamp));
  const blocks: React.ReactNode[] = [];
  sorted.forEach((episode, i) => {
    if (i > 0 && sorted[i - 1].segment_id !== episode.segment_id) {
      blocks.push(<GapMarker key={`gap-${setupName}-${i}`} />);
    }
    blocks.push(<EpisodeBlock key={`${setupName}-${episode.observed_start_timestamp}-${i}`} episode={episode} />);
  });

  return (
    <div className="flex items-center gap-2 border-b border-border py-2">
      <span className="w-48 shrink-0 font-mono text-xs text-foreground">{setupName}</span>
      <div className="flex flex-1 flex-wrap items-stretch gap-1 overflow-x-auto">
        {blocks.length === 0 ? <span className="text-xs text-muted">No episodes in this window.</span> : blocks}
      </div>
    </div>
  );
}

function ActivationEventRow({ event }: { event: LiveActivationEvent }) {
  return (
    <li data-testid="activation-event" className="flex items-center gap-2 text-xs text-muted">
      <span className="font-mono text-foreground">{formatClockCT(event.timestamp)}</span>
      <span>{event.segment_id}</span>
      <span className="text-foreground">{event.activated_setups.join(", ")}</span>
    </li>
  );
}

export function Timeline() {
  const { data, error, isError, isLoading } = useLiveEpisodes();

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Timeline</h2>
      {isError && <p className="text-sm text-danger">{error.message}</p>}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data && !data.found && <p className="text-sm text-muted">No MarketState has been ingested yet.</p>}
      {data?.found && (
        <>
          <div className="divide-y divide-border">
            {Object.entries(data.setups).map(([name, snapshot]) => {
              const episodes = [...snapshot.recent_episodes];
              if (snapshot.current_episode) episodes.push(snapshot.current_episode);
              return <SetupLane key={name} setupName={name} episodes={episodes} />;
            })}
          </div>

          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Activation Events</h3>
          {data.activation_events.length === 0 ? (
            <p className="text-xs text-muted">No activation events in this window.</p>
          ) : (
            <ul className="space-y-1">
              {data.activation_events.map((event, i) => (
                <ActivationEventRow key={`${event.timestamp}-${i}`} event={event} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

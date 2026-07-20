"""
UI v2, amendments 1 and 3. Projects RE-2's own, unmodified episode
construction (atlas.research.setup_profiling.service
.build_setup_profiling_dataset) onto a bounded, live repository window,
resolving the one genuine ambiguity a bounded window introduces: is an
episode that appears "left-censored" (starts at its segment's own first
bar) that way because a real market-data gap precedes it, or merely
because the query didn't fetch far enough back?

Design note (a refinement discovered while implementing this, not
predicted by the architecture sketch): build_setup_profiling_dataset()
already does everything needed here internally - load-agnostic filtering,
segment_by_gap, Rule/Setup Engine evaluation, and RE-2's own correct,
already-tested episode walk (termination_reason/is_left_censored). This
module does not re-implement that walk; it is a thin translation layer
that re-runs build_setup_profiling_dataset() against progressively wider
windows only when needed, and reinterprets its ALREADY-COMPUTED output:
TerminationReason.DATASET_END on the episode covering the window's own
latest bar means "still active" here (is_active=True) - the live-window
equivalent of "this is the most recent thing we know," never a claim that
nothing happens after it. Every other TerminationReason maps directly to
a genuinely observed, closed right boundary.

Left-boundary resolution needs no cross-iteration timestamp bookkeeping:
after any (re)fetch, an episode's segment being anything other than the
window's own FIRST segment (dataset.segments[0]) already proves a real
gap was found before it - by construction, segment_by_gap only creates a
new segment boundary at an actual missing-interval - so "not in the
first segment" is sufficient, on its own, to confirm left_boundary_reason
= segment_start, for both the currently-active episode and any closed
recent_episodes entry, without needing another fetch or a stored prior
boundary position.
"""
from typing import Optional

from atlas.core.primitives import Symbol, Timeframe
from atlas.live_view.models import (
    LeftBoundaryReason,
    LiveActivationEvent,
    LiveComputabilitySummary,
    LiveEpisodeProjection,
    LiveSetupSnapshot,
    LiveTerminationReason,
    LiveWindowResult,
    SegmentBoundary,
)
from atlas.market_engine.ports import MarketStateRepository
from atlas.profiling.models import ProfilingRunConfig
from atlas.research.setup_profiling import service as re2_service
from atlas.research.setup_profiling.models import SetupEpisode, TerminationReason
from atlas.setup_engine.models import SetupResult
from atlas.setup_engine.registry import REGISTRY as SETUP_REGISTRY

DEFAULT_WINDOW = 500
HARD_MAX_WINDOW = 5000
RECENT_EPISODES_LIMIT = 20

_TERMINATION_MAP: dict[TerminationReason, LiveTerminationReason] = {
    TerminationReason.BECAME_FALSE: LiveTerminationReason.BECAME_FALSE,
    TerminationReason.INSUFFICIENT_DATA: LiveTerminationReason.INSUFFICIENT_DATA,
    TerminationReason.SEGMENT_END: LiveTerminationReason.SEGMENT_END,
    # DATASET_END is deliberately absent - it is translated to is_active=True
    # by the caller, never surfaced as a LiveTerminationReason value.
}


async def _fetch_dataset(repository: MarketStateRepository, symbol: Symbol, timeframe: Timeframe, window: int):
    history = await repository.get_history(symbol, timeframe, limit=window)
    if not history:
        return None, []
    ascending = list(reversed(history))  # get_history is most-recent-first
    config = ProfilingRunConfig(
        symbol=symbol, timeframe=timeframe,
        start=ascending[0].envelope.occurred_at, end=ascending[-1].envelope.occurred_at,
        limit=len(ascending),
    )
    dataset = re2_service.build_setup_profiling_dataset(ascending, config)
    return dataset, ascending


def _find_active_episode(dataset, setup_name: str, latest_timestamp: str) -> Optional[SetupEpisode]:
    last_segment = dataset.segments[-1]
    for ep in dataset.episodes_by_setup[setup_name]:
        if (ep.segment_id == last_segment.segment_id and ep.end_timestamp == latest_timestamp
                and ep.termination_reason == TerminationReason.DATASET_END):
            return ep
    return None


def _observed_left_reason(dataset, episode: SetupEpisode) -> LeftBoundaryReason:
    """Only called when episode.is_left_censored is False - the bar
    immediately before the episode's start, within the same segment, is
    either a computable False (observed_activation) or InsufficientData
    (insufficient_data). Reads dataset's own per-segment index/outcome
    structures directly - the same lookup RE-2's own episode walk uses
    internally, not re-derived."""
    segment = dataset.segments_by_id[episode.segment_id]
    start_idx = segment.index_by_timestamp[episode.start_timestamp]
    prev_outcome = segment.outcome_by_name[start_idx - 1].get(episode.setup_name)
    if isinstance(prev_outcome, SetupResult):
        return LeftBoundaryReason.OBSERVED_ACTIVATION
    return LeftBoundaryReason.INSUFFICIENT_DATA


def _left_boundary_for_episode(dataset, episode: SetupEpisode) -> tuple[LeftBoundaryReason, bool]:
    """Returns (reason, is_window_truncated). Used for both a resolved
    currently-active episode and any closed recent_episodes entry - see
    module docstring for why "not the window's first segment" alone
    proves a genuine boundary, requiring no further fetch."""
    if not episode.is_left_censored:
        return _observed_left_reason(dataset, episode), False
    if episode.segment_id == dataset.segments[0].segment_id:
        return LeftBoundaryReason.QUERY_WINDOW_START, True
    return LeftBoundaryReason.SEGMENT_START, False


def _any_setup_still_ambiguous(dataset, ascending, setup_names) -> bool:
    latest_ts = ascending[-1].envelope.occurred_at.isoformat()
    for name in setup_names:
        ep = _find_active_episode(dataset, name, latest_ts)
        if ep is None:
            continue
        reason, _truncated = _left_boundary_for_episode(dataset, ep)
        if reason == LeftBoundaryReason.QUERY_WINDOW_START:
            return True
    return False


async def _resolve_window(repository, symbol, timeframe, setup_names, window, hard_max_window):
    """Widens the fetch window only while at least one setup's currently-
    active episode remains ambiguous (is_left_censored AND still in the
    window's own first segment), up to hard_max_window.

    Deliberately does NOT try to carry a per-setup "already resolved"
    episode object forward across widenings: widening rebuilds the ENTIRE
    shared dataset from a larger MarketState fetch, so segment_id (derived
    from a segment's own first bar, which can itself move earlier as more
    history is revealed) is not stable across dataset rebuilds even for a
    setup whose classification (observed_activation vs segment_start)
    would not change. An earlier version of this function tried to keep
    per-setup episode objects across iterations and let an already-
    resolved-in-an-earlier-iteration episode silently go stale relative
    to later widenings done for OTHER setups - caught by a real
    integration run, not a design review, where a setup active for the
    entire test dataset produced a KeyError trying to project a
    DATASET_END episode as a "recent" (closed) one. Fixed by classifying
    every setup fresh, exactly once, from one single final dataset -
    correctness by construction, and cheap enough (at most ~4 setups x
    ~4 widenings) that re-deriving is not worth the complexity of trying
    to cache it.

    Returns (dataset, ascending_states, actually_used_window,
    active_by_setup) where active_by_setup maps setup_name ->
    (SetupEpisode, LeftBoundaryReason, is_window_truncated) | None, all
    from the SAME final dataset."""
    dataset, ascending = await _fetch_dataset(repository, symbol, timeframe, window)
    if dataset is None or not dataset.segments:
        return None, [], window, {}

    while window < hard_max_window and _any_setup_still_ambiguous(dataset, ascending, setup_names):
        window = min(window * 2, hard_max_window)
        dataset, ascending = await _fetch_dataset(repository, symbol, timeframe, window)

    latest_ts = ascending[-1].envelope.occurred_at.isoformat()
    active_by_setup: dict = {}
    for name in setup_names:
        ep = _find_active_episode(dataset, name, latest_ts)
        if ep is None:
            active_by_setup[name] = None
            continue
        reason, truncated = _left_boundary_for_episode(dataset, ep)
        active_by_setup[name] = (ep, reason, truncated)

    return dataset, ascending, window, active_by_setup


def _project_episode(
    episode: SetupEpisode, left_reason: LeftBoundaryReason, is_window_truncated: bool,
    is_active: bool, latest_timestamp: str,
) -> LiveEpisodeProjection:
    activation_observed = left_reason in (LeftBoundaryReason.OBSERVED_ACTIVATION, LeftBoundaryReason.INSUFFICIENT_DATA)
    if is_active:
        end_timestamp_observed = None
        termination_reason = None
        right_boundary_observed = False
        last_observed_timestamp = latest_timestamp
        is_continuation = episode.start_timestamp != latest_timestamp
    else:
        end_timestamp_observed = episode.end_timestamp
        termination_reason = _TERMINATION_MAP[episode.termination_reason]
        right_boundary_observed = True
        last_observed_timestamp = episode.end_timestamp
        is_continuation = False  # not meaningful for a closed, historical episode - see recent_episodes docs

    return LiveEpisodeProjection(
        setup_name=episode.setup_name, segment_id=episode.segment_id,
        left_boundary_reason=left_reason,
        activation_timestamp_observed=episode.start_timestamp if activation_observed else None,
        observed_start_timestamp=episode.start_timestamp, duration_bars_observed=episode.duration_bars,
        is_window_truncated=is_window_truncated,
        is_active=is_active, last_observed_timestamp=last_observed_timestamp,
        end_timestamp_observed=end_timestamp_observed, termination_reason=termination_reason,
        right_boundary_observed=right_boundary_observed,
        is_continuation=is_continuation, start_state=episode.start_state, end_state=episode.end_state,
    )


def _computability_summary(records) -> LiveComputabilitySummary:
    computable = [r for r in records if r.computable]
    non_computable = [r for r in records if not r.computable]
    detected_true = sum(1 for r in computable if r.detected is True)
    reason_counts: dict[str, int] = {}
    for r in non_computable:
        reason_counts[r.insufficient_reason] = reason_counts.get(r.insufficient_reason, 0) + 1
    return LiveComputabilitySummary(
        computable_bars=len(computable), non_computable_bars=len(non_computable),
        detected_true_bars=detected_true, detected_false_bars=len(computable) - detected_true,
        insufficient_reason_counts=reason_counts,
    )


async def build_live_window_result(
    repository: MarketStateRepository, symbol: Symbol, timeframe: Timeframe,
    window: int = DEFAULT_WINDOW, hard_max_window: int = HARD_MAX_WINDOW,
    registry=SETUP_REGISTRY,
) -> Optional[LiveWindowResult]:
    """Pure with respect to persistence (reads only). Returns None if no
    MarketState has been ingested yet for (symbol, timeframe) - the same
    "nothing to evaluate" posture evaluate_latest_rule_engine_output
    already uses."""
    setup_names = [r.name for r in registry]
    dataset, ascending, actually_used_window, active_by_setup = await _resolve_window(
        repository, symbol, timeframe, setup_names, window, hard_max_window,
    )
    if dataset is None:
        return None

    latest_timestamp = ascending[-1].envelope.occurred_at.isoformat()
    warnings: list[str] = []
    setups: dict[str, LiveSetupSnapshot] = {}

    for name in setup_names:
        entry = active_by_setup.get(name)
        current_projection = None
        if entry is not None:
            episode, left_reason, is_truncated = entry
            current_projection = _project_episode(episode, left_reason, is_truncated, True, latest_timestamp)
            if is_truncated:
                warnings.append(f"window truncated while resolving {name}'s activation boundary")

        recent: list[LiveEpisodeProjection] = []
        for ep in sorted(dataset.episodes_by_setup[name], key=lambda e: e.start_timestamp, reverse=True):
            if (current_projection is not None and ep.start_timestamp == current_projection.observed_start_timestamp
                    and ep.segment_id == current_projection.segment_id):
                continue
            reason, truncated = _left_boundary_for_episode(dataset, ep)
            recent.append(_project_episode(ep, reason, truncated, False, latest_timestamp))
            if len(recent) >= RECENT_EPISODES_LIMIT:
                break

        setups[name] = LiveSetupSnapshot(
            setup_name=name, current_episode=current_projection, recent_episodes=tuple(recent),
            computability=_computability_summary(dataset.records_by_setup[name]),
        )

    segments = tuple(
        SegmentBoundary(
            segment_id=seg.segment_id,
            start_timestamp=seg.states[0].envelope.occurred_at.isoformat(),
            end_timestamp=None if seg.is_last else seg.states[-1].envelope.occurred_at.isoformat(),
        )
        for seg in dataset.segments
    )
    activation_events = tuple(
        LiveActivationEvent(timestamp=e.timestamp, segment_id=e.segment_id, activated_setups=e.activated_setups)
        for e in dataset.activation_events
    )

    return LiveWindowResult(
        requested_window=window, actually_used_window=actually_used_window, data_as_of=latest_timestamp,
        setups=setups, segments=segments, activation_events=activation_events, warnings=tuple(warnings),
    )

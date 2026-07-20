"""
Sprint RE-2. Pure computation core for episode-aware Setup Engine profiling.

Reuses, unchanged: atlas.profiling.service.filter_input_states/.segment_by_gap
(gap/segment detection - never re-implemented here), atlas.rule_engine
.service.build_rule_engine_output_window and atlas.setup_engine.service
.build_setup_engine_output_window (fact/setup evaluation - never duplicated
here; this module only reads already-computed SetupOutcome/FactOutcome
values), and atlas.research.statistical_profiling.models.RunManifest
(read-only reuse of a metadata shape, RE-1's frozen core untouched).

Every public build_* function below is pure - no repository, no I/O, no
wall-clock read (generated_at is a caller-supplied parameter, the same
determinism rule RE-1's build_statistical_profile already follows). All six
report builders share one `_Dataset` built once (`build_setup_profiling_dataset`) so
Rule/Setup Engine evaluation runs exactly once per input bar regardless of
how many reports are generated from it.
"""
import bisect
import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from atlas.market_engine.models import MarketState
from atlas.profiling.models import ProfilingRunConfig
from atlas.profiling.service import filter_input_states, segment_by_gap
from atlas.research.service import current_code_version
from atlas.research.setup_profiling.models import (
    REGISTERED_FACT_NAMES,
    ActivationEvent,
    ActivationOverlapMetrics,
    ActivationProximityMetrics,
    BurstProfile,
    ComputabilityProfile,
    ContextOffsetProfile,
    EpisodeContainmentMetrics,
    EpisodeIntersectionMetrics,
    EpisodeTransition,
    FactContextStats,
    InterEpisodeGap,
    NumericStats,
    OverlapMetrics,
    RegisteredFactSnapshot,
    RunManifest,
    SetupClustering,
    SetupClusteringEntry,
    SetupComputabilityRecord,
    SetupContextProfile,
    SetupContextProfileEntry,
    SetupEpisode,
    SetupOverlap,
    SetupOverlapEntry,
    SetupProfile,
    SetupProfileEntry,
    SetupTimeDistribution,
    SetupTimeDistributionEntry,
    SetupTransitions,
    TerminationReason,
    TimeBucketCount,
    TransitionMatrixEntry,
)
from atlas.research.setup_profiling.relationships import relationship_for
from atlas.rule_engine.models import FactResult, RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import SetupEngineOutput, SetupResult
from atlas.setup_engine.registration import SetupRegistration
from atlas.setup_engine.registry import REGISTRY
from atlas.setup_engine.service import build_setup_engine_output_window

SCHEMA_VERSION = "1.0"

_CT = ZoneInfo("America/Chicago")  # same convention atlas.monitoring.py and RE-1 already establish
_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Report 3's "repeat activation within N minutes" metric (original RE-2 spec,
# unmodified by amendment 9) and its burst/cluster threshold set (amendment
# 9: report at every one of these, never a single "canonical" choice) are
# deliberately two different threshold lists - see amendment 9's own
# discussion for why 120 stays in the repeat-within metric but not bursts.
REPEAT_WITHIN_THRESHOLDS_MINUTES: tuple[int, ...] = (15, 30, 60, 120)
CLUSTER_THRESHOLDS_MINUTES: tuple[int, ...] = (15, 30, 60)
ACTIVATION_PROXIMITY_THRESHOLDS_MINUTES: tuple[int, ...] = (5, 15, 30)

_CONTEXT_OFFSETS: tuple[tuple[str, int], ...] = (("-1", -1), ("activation", 0), ("+1", 1), ("+3", 3))


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _percentile(ordered: list[float], p: float) -> float:
    """Nearest-rank percentile - identical method to
    atlas.profiling.service._percentile / RE-1's own copy; a fresh, small,
    per-module copy rather than a cross-package private import, matching
    this codebase's own established precedent (RE-1's service.py docstring
    explains the same choice for its copy)."""
    n = len(ordered)
    rank = max(1, min(n, math.ceil(p / 100 * n)))
    return ordered[rank - 1]


def _numeric_stats(values: list[float]) -> NumericStats:
    if not values:
        return NumericStats(count=0, mean=None, median=None, p75=None, p90=None, p95=None, max=None)
    ordered = sorted(values)
    return NumericStats(
        count=len(values), mean=sum(values) / len(values),
        median=_percentile(ordered, 50), p75=_percentile(ordered, 75),
        p90=_percentile(ordered, 90), p95=_percentile(ordered, 95), max=ordered[-1],
    )


def _pearson_correlation(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x == 0 or variance_y == 0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def _fact_value(rule_output: RuleEngineOutput, fact_name: str):
    outcome = rule_output.facts[fact_name]
    return outcome.value if isinstance(outcome, FactResult) else None


def build_registered_fact_snapshot(rule_output: RuleEngineOutput) -> RegisteredFactSnapshot:
    return RegisteredFactSnapshot(**{name: _fact_value(rule_output, name) for name in REGISTERED_FACT_NAMES})


def _session_key(state: MarketState) -> str:
    return state.session_name.value if state.session_name is not None else "unknown"


def _hour_key(state: MarketState) -> str:
    return f"{state.envelope.occurred_at.astimezone(_CT).hour:02d}:00"


def _weekday_key(state: MarketState) -> str:
    return _WEEKDAY_NAMES[state.envelope.occurred_at.astimezone(_CT).weekday()]


def _month_key(state: MarketState) -> str:
    ct = state.envelope.occurred_at.astimezone(_CT)
    return f"{ct.year:04d}-{ct.month:02d}"


class _Segment:
    """Private, per-segment substrate every report builder reads from - one
    Rule/Setup Engine evaluation pass, shared across all six reports."""

    __slots__ = (
        "segment_id", "is_last", "states", "rule_outputs", "setup_outputs", "outcome_by_name",
        "index_by_timestamp",
    )

    def __init__(self, states: list[MarketState], rule_outputs: list[RuleEngineOutput],
                 setup_outputs: list[SetupEngineOutput], is_last: bool) -> None:
        self.states = states
        self.rule_outputs = rule_outputs
        self.setup_outputs = setup_outputs
        self.is_last = is_last
        self.segment_id = states[0].envelope.occurred_at.isoformat()
        self.outcome_by_name: list[dict] = [
            {outcome.setup_name: outcome for outcome in output.setups} for output in setup_outputs
        ]
        self.index_by_timestamp: dict[str, int] = {
            s.envelope.occurred_at.isoformat(): idx for idx, s in enumerate(states)
        }

    def __len__(self) -> int:
        return len(self.states)


class _Dataset:
    """Private orchestration result: every segment, every setup's episodes
    and computability records, and every ActivationEvent - built once by
    build_setup_profiling_dataset, consumed by all six public build_* report functions."""

    __slots__ = (
        "segments", "segments_by_id", "setup_names", "episodes_by_setup", "records_by_setup",
        "activation_events", "activation_events_by_segment",
    )

    def __init__(self, segments, setup_names, episodes_by_setup, records_by_setup, activation_events) -> None:
        self.segments = segments
        self.segments_by_id = {s.segment_id: s for s in segments}
        self.setup_names = setup_names
        self.episodes_by_setup = episodes_by_setup
        self.records_by_setup = records_by_setup
        self.activation_events = activation_events
        by_segment: dict[str, list[ActivationEvent]] = {}
        for event in activation_events:
            by_segment.setdefault(event.segment_id, []).append(event)
        for events in by_segment.values():
            events.sort(key=lambda e: e.timestamp)
        self.activation_events_by_segment = by_segment


def _episode_metadata_from_state(state: MarketState) -> dict:
    return {
        "session": _session_key(state),
        "hour_ct": _hour_key(state),
        "weekday_ct": _weekday_key(state),
        "trading_date": state.trading_date.isoformat() if state.trading_date is not None else "unknown",
    }


def _walk_setup_in_segment(setup_name: str, segment: _Segment) -> tuple[list[SetupEpisode], list[SetupComputabilityRecord]]:
    """The one run-boundary walk this package owns (amendment 1's
    termination/censoring rules) - never bridges an InsufficientData
    position or the segment's own boundary. Returns (episodes, computability
    records) for this setup within this one segment."""
    episodes: list[SetupEpisode] = []
    records: list[SetupComputabilityRecord] = []

    n = len(segment)
    active_start_idx: Optional[int] = None

    def _close(start_idx: int, end_idx: int, reason: TerminationReason) -> None:
        start_state = segment.states[start_idx]
        end_state = segment.states[end_idx]
        meta = _episode_metadata_from_state(start_state)
        episodes.append(SetupEpisode(
            setup_name=setup_name,
            segment_id=segment.segment_id,
            start_timestamp=start_state.envelope.occurred_at.isoformat(),
            end_timestamp=end_state.envelope.occurred_at.isoformat(),
            duration_bars=end_idx - start_idx + 1,
            start_state=build_registered_fact_snapshot(segment.rule_outputs[start_idx]),
            end_state=build_registered_fact_snapshot(segment.rule_outputs[end_idx]),
            session=meta["session"], hour_ct=meta["hour_ct"], weekday_ct=meta["weekday_ct"],
            trading_date=meta["trading_date"],
            termination_reason=reason,
            is_left_censored=(start_idx == 0),
            is_right_censored=(reason != TerminationReason.BECAME_FALSE),
        ))

    for i in range(n):
        outcome = segment.outcome_by_name[i].get(setup_name)
        computable = isinstance(outcome, SetupResult)
        detected = outcome.detected if computable else None
        reason = None if computable else outcome.reason
        timestamp = segment.states[i].envelope.occurred_at.isoformat()
        records.append(SetupComputabilityRecord(
            timestamp=timestamp, computable=computable, detected=detected, insufficient_reason=reason,
        ))

        if computable and detected is True:
            if active_start_idx is None:
                active_start_idx = i
            continue

        if active_start_idx is not None:
            close_reason = TerminationReason.BECAME_FALSE if computable else TerminationReason.INSUFFICIENT_DATA
            _close(active_start_idx, i - 1, close_reason)
            active_start_idx = None

    if active_start_idx is not None:
        close_reason = TerminationReason.DATASET_END if segment.is_last else TerminationReason.SEGMENT_END
        _close(active_start_idx, n - 1, close_reason)

    return episodes, records


def _build_activation_events(all_episodes: list[SetupEpisode]) -> list[ActivationEvent]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for ep in all_episodes:
        grouped.setdefault((ep.segment_id, ep.start_timestamp), []).append(ep.setup_name)
    events = [
        ActivationEvent(timestamp=ts, segment_id=seg, activated_setups=tuple(names))
        for (seg, ts), names in grouped.items()
    ]
    events.sort(key=lambda e: e.timestamp)
    return events


def build_setup_profiling_dataset(
    states: list[MarketState], config: ProfilingRunConfig, registry: tuple[SetupRegistration, ...] = REGISTRY,
) -> _Dataset:
    filtered, _excluded_forming, _excluded_synthetic = filter_input_states(states, config.excluded_symbols)
    raw_segments = segment_by_gap(filtered)
    setup_names = [r.name for r in registry]

    segments: list[_Segment] = []
    for i, raw_segment in enumerate(raw_segments):
        rule_outputs = build_rule_engine_output_window(raw_segment)
        setup_outputs = build_setup_engine_output_window(rule_outputs, registry)
        segments.append(_Segment(raw_segment, rule_outputs, setup_outputs, is_last=(i == len(raw_segments) - 1)))

    episodes_by_setup: dict[str, list[SetupEpisode]] = {name: [] for name in setup_names}
    records_by_setup: dict[str, list[SetupComputabilityRecord]] = {name: [] for name in setup_names}
    for segment in segments:
        for name in setup_names:
            episodes, records = _walk_setup_in_segment(name, segment)
            episodes_by_setup[name].extend(episodes)
            records_by_setup[name].extend(records)

    all_episodes = [ep for eps in episodes_by_setup.values() for ep in eps]
    activation_events = _build_activation_events(all_episodes)

    return _Dataset(segments, setup_names, episodes_by_setup, records_by_setup, activation_events)


def build_run_manifest(
    config: ProfilingRunConfig, row_count: int, generated_at: datetime, source_description: str,
) -> RunManifest:
    return RunManifest(
        schema_version=SCHEMA_VERSION,
        symbol=config.symbol.ticker, timeframe=config.timeframe.value,
        requested_start=config.start.isoformat(), requested_end=config.end.isoformat(),
        source_description=source_description, row_count=row_count,
        generated_at=generated_at.astimezone(timezone.utc).isoformat(),
        code_version=current_code_version(),
    )


def _eligible_trading_dates(setup_name: str, dataset: _Dataset) -> set[str]:
    """Amendment 10: a trading day is eligible for a setup if it has at
    least one COMPUTABLE (not necessarily active) observation for that
    setup - never gated on detected=True."""
    dates: set[str] = set()
    for segment in dataset.segments:
        for i, state in enumerate(segment.states):
            outcome = segment.outcome_by_name[i].get(setup_name)
            if isinstance(outcome, SetupResult) and state.trading_date is not None:
                dates.add(state.trading_date.isoformat())
    return dates


# ---------------------------------------------------------------------------
# Report 1: RE2_Setup_Profile.md
# ---------------------------------------------------------------------------

def build_setup_profile(dataset: _Dataset, manifest: RunManifest) -> SetupProfile:
    entries: list[SetupProfileEntry] = []
    computability_profiles: list[ComputabilityProfile] = []

    for name in dataset.setup_names:
        records = dataset.records_by_setup[name]
        episodes = dataset.episodes_by_setup[name]

        computable = [r for r in records if r.computable]
        non_computable = [r for r in records if not r.computable]
        detected_true = sum(1 for r in computable if r.detected is True)
        detected_false = len(computable) - detected_true
        reason_counts: dict[str, int] = {}
        for r in non_computable:
            reason_counts[r.insufficient_reason] = reason_counts.get(r.insufficient_reason, 0) + 1
        computability_profiles.append(ComputabilityProfile(
            setup_name=name, total_bars=len(records), computable_bars=len(computable),
            non_computable_bars=len(non_computable), detected_true_bars=detected_true,
            detected_false_bars=detected_false, insufficient_reason_counts=reason_counts,
        ))

        all_durations = [float(ep.duration_bars) for ep in episodes]
        fully_observed = [ep for ep in episodes if ep.is_fully_observed]
        fully_observed_durations = [float(ep.duration_bars) for ep in fully_observed]

        single_bar = sum(1 for ep in episodes if ep.duration_bars == 1)
        activation_bar_count = len(episodes)
        continuation_bar_count = detected_true - activation_bar_count

        eligible_dates = _eligible_trading_dates(name, dataset)
        activation_dates = {ep.trading_date for ep in episodes}
        left_censored = sum(1 for ep in episodes if ep.is_left_censored)
        right_censored = sum(1 for ep in episodes if ep.is_right_censored)

        entries.append(SetupProfileEntry(
            setup_name=name,
            computable_bars=len(computable),
            active_bars=detected_true,
            active_bar_rate=(detected_true / len(computable)) if computable else None,
            episode_count=len(episodes),
            all_episodes_duration=_numeric_stats(all_durations),
            fully_observed_duration=_numeric_stats(fully_observed_durations),
            single_bar_episode_count=single_bar,
            multi_bar_episode_count=len(episodes) - single_bar,
            activation_bar_count=activation_bar_count,
            continuation_bar_count=continuation_bar_count,
            eligible_trading_days=len(eligible_dates),
            episodes_per_trading_day=(len(episodes) / len(eligible_dates)) if eligible_dates else None,
            days_with_activation_count=len(activation_dates),
            days_with_activation_rate=(len(activation_dates) / len(eligible_dates)) if eligible_dates else None,
            left_censored_count=left_censored,
            right_censored_count=right_censored,
            fully_observed_count=len(fully_observed),
        ))

    return SetupProfile(manifest=manifest, entries=tuple(entries), computability=tuple(computability_profiles))


# ---------------------------------------------------------------------------
# Report 2: RE2_Time_Distribution.md (amendment 3)
# ---------------------------------------------------------------------------

def _time_bucket_denominators(setup_name: str, dataset: _Dataset) -> dict[str, dict[str, dict]]:
    """Per bucket dimension, per bucket key: eligible (computable) bar
    count, active bar count, and the set of trading dates observed there -
    the explicit denominators amendment 3 requires, computed once per bar
    (never inferred from activation counts alone)."""
    dims: dict[str, dict[str, dict]] = {"session": {}, "hour": {}, "weekday": {}, "month": {}}
    for segment in dataset.segments:
        for i, state in enumerate(segment.states):
            outcome = segment.outcome_by_name[i].get(setup_name)
            if not isinstance(outcome, SetupResult):
                continue
            keys = {
                "session": _session_key(state), "hour": _hour_key(state),
                "weekday": _weekday_key(state), "month": _month_key(state),
            }
            for dim, key in keys.items():
                bucket = dims[dim].setdefault(key, {"eligible": 0, "active": 0, "dates": set()})
                bucket["eligible"] += 1
                if outcome.detected is True:
                    bucket["active"] += 1
                if state.trading_date is not None:
                    bucket["dates"].add(state.trading_date.isoformat())
    return dims


def _month_key_from_iso(iso_ts: str) -> str:
    ct = _parse_iso(iso_ts).astimezone(_CT)
    return f"{ct.year:04d}-{ct.month:02d}"


def _activation_counts_by_bucket(episodes: list[SetupEpisode]) -> dict[str, dict[str, int]]:
    """Amendment 3: activation distribution buckets by the first bar of
    each episode - the sole activation-side metric (the former "unique
    episode count" comparison is removed as definitionally redundant with
    this)."""
    dims: dict[str, dict[str, int]] = {"session": {}, "hour": {}, "weekday": {}, "month": {}}
    for ep in episodes:
        keys = {
            "session": ep.session, "hour": ep.hour_ct, "weekday": ep.weekday_ct,
            "month": _month_key_from_iso(ep.start_timestamp),
        }
        for dim, key in keys.items():
            dims[dim][key] = dims[dim].get(key, 0) + 1
    return dims


def _time_bucket_counts(denominators: dict[str, dict], activations: dict[str, int]) -> dict[str, TimeBucketCount]:
    all_keys = set(denominators) | set(activations)
    result: dict[str, TimeBucketCount] = {}
    for key in all_keys:
        denom = denominators.get(key, {"eligible": 0, "active": 0, "dates": set()})
        activation_count = activations.get(key, 0)
        eligible = denom["eligible"]
        eligible_days = len(denom["dates"])
        result[key] = TimeBucketCount(
            bucket_key=key,
            activation_count=activation_count,
            active_bar_count=denom["active"],
            eligible_bar_count=eligible,
            eligible_trading_days=eligible_days,
            activation_rate_per_eligible_bar=(activation_count / eligible) if eligible else None,
            activation_rate_per_trading_day=(activation_count / eligible_days) if eligible_days else None,
            active_bar_rate_per_eligible_bar=(denom["active"] / eligible) if eligible else None,
        )
    return result


def build_time_distribution(dataset: _Dataset, manifest: RunManifest) -> SetupTimeDistribution:
    entries: list[SetupTimeDistributionEntry] = []
    for name in dataset.setup_names:
        denom = _time_bucket_denominators(name, dataset)
        act = _activation_counts_by_bucket(dataset.episodes_by_setup[name])

        def _ordered(dim: str, key_order: Optional[tuple] = None) -> tuple:
            counts = _time_bucket_counts(denom[dim], act[dim])
            if key_order is None:
                return tuple(counts[k] for k in sorted(counts))
            order = {k: i for i, k in enumerate(key_order)}
            return tuple(counts[k] for k in sorted(counts, key=lambda k: order.get(k, len(order))))

        entries.append(SetupTimeDistributionEntry(
            setup_name=name,
            by_session=_ordered("session"),
            by_hour_ct=_ordered("hour"),
            by_weekday_ct=_ordered("weekday", _WEEKDAY_NAMES),
            by_month=_ordered("month"),
        ))
    return SetupTimeDistribution(manifest=manifest, entries=tuple(entries))


# ---------------------------------------------------------------------------
# Report 3: RE2_Clustering.md (amendment 9)
# ---------------------------------------------------------------------------

def _episodes_by_segment_sorted(episodes: list[SetupEpisode]) -> dict[str, list[SetupEpisode]]:
    grouped: dict[str, list[SetupEpisode]] = {}
    for ep in episodes:
        grouped.setdefault(ep.segment_id, []).append(ep)
    for eps in grouped.values():
        eps.sort(key=lambda e: e.start_timestamp)
    return grouped


def _within_segment_gaps(setup_name: str, by_segment: dict[str, list[SetupEpisode]]) -> tuple[list[InterEpisodeGap], int]:
    """Amendment 9: inter-episode time computed ONLY within the same
    segment; the last episode of each segment has no within-segment
    successor and is counted as censored_by_gap rather than contributing a
    fabricated cross-gap duration to the distribution."""
    gaps: list[InterEpisodeGap] = []
    censored = 0
    for episodes in by_segment.values():
        for idx, ep in enumerate(episodes):
            if idx == len(episodes) - 1:
                censored += 1
                continue
            nxt = episodes[idx + 1]
            gap_minutes = (_parse_iso(nxt.start_timestamp) - _parse_iso(ep.end_timestamp)).total_seconds() / 60
            gaps.append(InterEpisodeGap(
                setup_name=setup_name, from_episode_end=ep.end_timestamp,
                to_episode_start=nxt.start_timestamp, gap_minutes=gap_minutes,
            ))
    return gaps, censored


def _bursts_for_threshold(by_segment: dict[str, list[SetupEpisode]], threshold_minutes: int) -> BurstProfile:
    """A burst is a maximal run of within-segment-consecutive episodes
    where every consecutive gap is <= threshold_minutes - reported at every
    threshold in CLUSTER_THRESHOLDS_MINUTES, never one "canonical" choice
    (amendment 9)."""
    burst_sizes: list[int] = []
    for episodes in by_segment.values():
        if not episodes:
            continue
        size = 1
        for prev, nxt in zip(episodes, episodes[1:]):
            gap = (_parse_iso(nxt.start_timestamp) - _parse_iso(prev.end_timestamp)).total_seconds() / 60
            if gap <= threshold_minutes:
                size += 1
            else:
                burst_sizes.append(size)
                size = 1
        burst_sizes.append(size)
    return BurstProfile(
        threshold_minutes=threshold_minutes, burst_count=len(burst_sizes),
        burst_sizes=tuple(burst_sizes), longest_burst_size=max(burst_sizes, default=0),
    )


def build_clustering(dataset: _Dataset, manifest: RunManifest) -> SetupClustering:
    entries: list[SetupClusteringEntry] = []
    for name in dataset.setup_names:
        episodes = dataset.episodes_by_setup[name]
        by_segment = _episodes_by_segment_sorted(episodes)
        gaps, censored = _within_segment_gaps(name, by_segment)
        gap_minutes = [g.gap_minutes for g in gaps]
        repeat_within = {t: sum(1 for g in gap_minutes if g <= t) for t in REPEAT_WITHIN_THRESHOLDS_MINUTES}
        bursts = tuple(_bursts_for_threshold(by_segment, t) for t in CLUSTER_THRESHOLDS_MINUTES)
        eligible_dates = _eligible_trading_dates(name, dataset)
        entries.append(SetupClusteringEntry(
            setup_name=name,
            within_segment_gap_count=len(gaps),
            censored_by_gap_count=censored,
            gap_minutes_stats=_numeric_stats(gap_minutes),
            repeat_within_minutes=repeat_within,
            episodes_per_trading_day=(len(episodes) / len(eligible_dates)) if eligible_dates else None,
            bursts=bursts,
        ))
    return SetupClustering(manifest=manifest, entries=tuple(entries))


# ---------------------------------------------------------------------------
# Report 4: RE2_Setup_Overlap.md (amendment 4)
# ---------------------------------------------------------------------------

def _active_bar_overlap(records_a: list[SetupComputabilityRecord], records_b: list[SetupComputabilityRecord]) -> OverlapMetrics:
    pairs = [(ra, rb) for ra, rb in zip(records_a, records_b) if ra.computable and rb.computable]
    n = len(pairs)
    if n == 0:
        return OverlapMetrics(0, None, None, None, None, None, None, None)
    a_flags = [1.0 if ra.detected is True else 0.0 for ra, _rb in pairs]
    b_flags = [1.0 if rb.detected is True else 0.0 for _ra, rb in pairs]
    a_true, b_true = sum(a_flags), sum(b_flags)
    both_true = sum(1 for a, b in zip(a_flags, b_flags) if a == 1.0 and b == 1.0)
    p_a, p_b, p_both = a_true / n, b_true / n, both_true / n
    lift = (p_both / (p_a * p_b)) if p_a > 0 and p_b > 0 else None
    conditional = (both_true / b_true) if b_true > 0 else None
    union = a_true + b_true - both_true
    jaccard = (both_true / union) if union > 0 else None
    correlation = _pearson_correlation(a_flags, b_flags)
    return OverlapMetrics(
        jointly_computable_bars=n, p_a_active=p_a, p_b_active=p_b, p_both_active=p_both,
        lift=lift, correlation=correlation, conditional_p_a_given_b=conditional, jaccard_active_bars=jaccard,
    )


def _activation_overlap(episodes_a: list[SetupEpisode], episodes_b: list[SetupEpisode]) -> ActivationOverlapMetrics:
    a_starts = {(ep.segment_id, ep.start_timestamp) for ep in episodes_a}
    b_starts = {(ep.segment_id, ep.start_timestamp) for ep in episodes_b}
    same_bar = a_starts & b_starts
    a_n, b_n = len(a_starts), len(b_starts)
    return ActivationOverlapMetrics(
        same_bar_activation_count=len(same_bar), a_activation_count=a_n, b_activation_count=b_n,
        p_same_bar_given_a=(len(same_bar) / a_n) if a_n else None,
        p_same_bar_given_b=(len(same_bar) / b_n) if b_n else None,
    )


def _sweep_episode_overlaps(
    episodes_a: list[SetupEpisode], episodes_b: list[SetupEpisode],
) -> tuple[int, int, int, int, int]:
    """Standard sorted-interval-list sweep: advances whichever interval
    ends first, so every overlapping pair is found exactly once even when
    one interval overlaps several of the other's (a long liquidity_sweep
    run overlapping several shorter displacement episodes, for instance).
    Returns (overlapping_pair_count, a_episodes_intersecting,
    b_episodes_intersecting, a_contained_in_b, b_contained_in_a). Since a
    single setup's own episodes never overlap each other (by construction -
    each is a maximal run), at most one b interval can ever fully contain a
    given a interval, and vice versa."""
    a = sorted(episodes_a, key=lambda e: e.start_timestamp)
    b = sorted(episodes_b, key=lambda e: e.start_timestamp)
    i = j = 0
    overlapping_pairs = 0
    intersecting_a: set[int] = set()
    intersecting_b: set[int] = set()
    contained_a_in_b: set[int] = set()
    contained_b_in_a: set[int] = set()
    while i < len(a) and j < len(b):
        ea, eb = a[i], b[j]
        if ea.start_timestamp <= eb.end_timestamp and eb.start_timestamp <= ea.end_timestamp:
            overlapping_pairs += 1
            intersecting_a.add(i)
            intersecting_b.add(j)
            if eb.start_timestamp <= ea.start_timestamp and ea.end_timestamp <= eb.end_timestamp:
                contained_a_in_b.add(i)
            if ea.start_timestamp <= eb.start_timestamp and eb.end_timestamp <= ea.end_timestamp:
                contained_b_in_a.add(j)
        if ea.end_timestamp <= eb.end_timestamp:
            i += 1
        else:
            j += 1
    return overlapping_pairs, len(intersecting_a), len(intersecting_b), len(contained_a_in_b), len(contained_b_in_a)


def _episode_intersection_and_containment(
    episodes_a: list[SetupEpisode], episodes_b: list[SetupEpisode],
) -> tuple[EpisodeIntersectionMetrics, EpisodeContainmentMetrics]:
    pairs, ia, ib, cab, cba = _sweep_episode_overlaps(episodes_a, episodes_b)
    a_n, b_n = len(episodes_a), len(episodes_b)
    intersection = EpisodeIntersectionMetrics(
        intersecting_pair_count=pairs, a_episode_count=a_n, b_episode_count=b_n,
        rate_of_a_episodes_intersecting=(ia / a_n) if a_n else None,
        rate_of_b_episodes_intersecting=(ib / b_n) if b_n else None,
    )
    containment = EpisodeContainmentMetrics(a_contained_in_b_count=cab, b_contained_in_a_count=cba)
    return intersection, containment


def _activation_proximity(
    episodes_a: list[SetupEpisode], episodes_b: list[SetupEpisode], threshold_minutes: int,
) -> ActivationProximityMetrics:
    a_times = sorted(_parse_iso(ep.start_timestamp) for ep in episodes_a)
    b_times = sorted(_parse_iso(ep.start_timestamp) for ep in episodes_b)
    delta = timedelta(minutes=threshold_minutes)

    def _count_with_nearby(xs: list[datetime], ys: list[datetime]) -> int:
        j_lo, n_y, count = 0, len(ys), 0
        for x in xs:
            while j_lo < n_y and ys[j_lo] < x - delta:
                j_lo += 1
            j, found = j_lo, False
            while j < n_y and ys[j] <= x + delta:
                found = True
                j += 1
            if found:
                count += 1
        return count

    return ActivationProximityMetrics(
        threshold_minutes=threshold_minutes,
        a_activations_with_nearby_b=_count_with_nearby(a_times, b_times),
        b_activations_with_nearby_a=_count_with_nearby(b_times, a_times),
    )


def build_overlap(dataset: _Dataset, manifest: RunManifest) -> SetupOverlap:
    entries: list[SetupOverlapEntry] = []
    names = dataset.setup_names
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            episodes_a, episodes_b = dataset.episodes_by_setup[a], dataset.episodes_by_setup[b]
            intersection, containment = _episode_intersection_and_containment(episodes_a, episodes_b)
            entries.append(SetupOverlapEntry(
                setup_a=a, setup_b=b, relationship=relationship_for(a, b),
                active_bar_overlap=_active_bar_overlap(dataset.records_by_setup[a], dataset.records_by_setup[b]),
                activation_overlap=_activation_overlap(episodes_a, episodes_b),
                episode_intersection=intersection, episode_containment=containment,
                activation_proximity=tuple(
                    _activation_proximity(episodes_a, episodes_b, t) for t in ACTIVATION_PROXIMITY_THRESHOLDS_MINUTES
                ),
            ))
    return SetupOverlap(manifest=manifest, entries=tuple(entries))


# ---------------------------------------------------------------------------
# Report 5: RE2_Context_Profile.md (amendments 6, 7)
# ---------------------------------------------------------------------------

def _fact_context_stats_for_offset(
    fact_name: str, snapshots: list[Optional[RegisteredFactSnapshot]],
) -> FactContextStats:
    """amendment 6: bar availability (was there a bar at all at this
    offset, within the same segment) is tracked at the ContextOffsetProfile
    level via episode_count vs bar_available_count here; per-fact
    computability is tracked independently - a bar being available never
    implies every fact was computable there, and one fact's InsufficientData
    never hides another fact's real value at the same bar."""
    bar_available = [s for s in snapshots if s is not None]
    bar_unavailable_count = len(snapshots) - len(bar_available)
    values = [s.value_of(fact_name) for s in bar_available]
    computable_values = [v for v in values if v is not None]
    insufficient_count = len(values) - len(computable_values)

    boolean_true_rate = None
    enum_value_counts: dict[str, int] = {}
    if fact_name in {"volume_spike", "displacement", "rejection", "liquidity_sweep", "reclaim"}:
        if computable_values:
            boolean_true_rate = sum(1 for v in computable_values if v is True) / len(computable_values)
    else:
        for v in computable_values:
            enum_value_counts[v] = enum_value_counts.get(v, 0) + 1

    return FactContextStats(
        fact_name=fact_name,
        bar_available_count=len(bar_available), bar_unavailable_count=bar_unavailable_count,
        computable_count=len(computable_values), insufficient_count=insufficient_count,
        boolean_true_rate=boolean_true_rate, enum_value_counts=enum_value_counts,
    )


def _context_snapshot_at_offset(dataset: _Dataset, episode: SetupEpisode, offset: int) -> Optional[RegisteredFactSnapshot]:
    segment = dataset.segments_by_id[episode.segment_id]
    start_idx = segment.index_by_timestamp[episode.start_timestamp]
    target_idx = start_idx + offset
    if target_idx < 0 or target_idx >= len(segment):
        return None
    return build_registered_fact_snapshot(segment.rule_outputs[target_idx])


def _context_bucket_at_offset(dataset: _Dataset, episode: SetupEpisode, offset: int) -> Optional[MarketState]:
    segment = dataset.segments_by_id[episode.segment_id]
    start_idx = segment.index_by_timestamp[episode.start_timestamp]
    target_idx = start_idx + offset
    if target_idx < 0 or target_idx >= len(segment):
        return None
    return segment.states[target_idx]


def _build_context_offset_profile(dataset: _Dataset, episodes: list[SetupEpisode], label: str, offset: int) -> ContextOffsetProfile:
    snapshots = [_context_snapshot_at_offset(dataset, ep, offset) for ep in episodes]
    bars = [_context_bucket_at_offset(dataset, ep, offset) for ep in episodes]

    session_counts: dict[str, int] = {}
    hour_counts: dict[str, int] = {}
    weekday_counts: dict[str, int] = {}
    for state in bars:
        if state is None:
            continue
        session_counts[_session_key(state)] = session_counts.get(_session_key(state), 0) + 1
        hour_counts[_hour_key(state)] = hour_counts.get(_hour_key(state), 0) + 1
        weekday_counts[_weekday_key(state)] = weekday_counts.get(_weekday_key(state), 0) + 1

    facts = tuple(
        _fact_context_stats_for_offset(name, snapshots) for name in REGISTERED_FACT_NAMES
    )
    return ContextOffsetProfile(
        offset_label=label, episode_count=len(episodes), facts=facts,
        session_counts=session_counts, hour_counts=hour_counts, weekday_counts=weekday_counts,
    )


def build_context_profile(dataset: _Dataset, manifest: RunManifest) -> SetupContextProfile:
    entries: list[SetupContextProfileEntry] = []
    for name in dataset.setup_names:
        episodes = dataset.episodes_by_setup[name]
        offsets = tuple(
            _build_context_offset_profile(dataset, episodes, label, offset)
            for label, offset in _CONTEXT_OFFSETS
        )
        entries.append(SetupContextProfileEntry(setup_name=name, offsets=offsets))
    return SetupContextProfile(manifest=manifest, entries=tuple(entries))


# ---------------------------------------------------------------------------
# Report 6: RE2_Setup_Transitions.md (amendment 8)
# ---------------------------------------------------------------------------

def _next_activation_event(dataset: _Dataset, episode: SetupEpisode) -> tuple[Optional[ActivationEvent], bool]:
    """Earliest ActivationEvent strictly after this episode's end,
    WITHIN THE SAME SEGMENT (amendment 8/9 - never resolved across a
    segment boundary). Returns (event_or_None, is_last_segment)."""
    segment = dataset.segments_by_id[episode.segment_id]
    events = dataset.activation_events_by_segment.get(episode.segment_id, [])
    timestamps = [e.timestamp for e in events]
    idx = bisect.bisect_right(timestamps, episode.end_timestamp)
    if idx < len(events):
        return events[idx], segment.is_last
    return None, segment.is_last


def build_transitions(dataset: _Dataset, manifest: RunManifest) -> SetupTransitions:
    all_episodes = [ep for eps in dataset.episodes_by_setup.values() for ep in eps]
    transitions: list[EpisodeTransition] = []
    matrix_counts: dict[str, dict[str, int]] = {name: {} for name in dataset.setup_names}
    same_setup_totals: dict[str, list[int]] = {name: [0, 0] for name in dataset.setup_names}  # [same_count, total]
    cross_setup_totals: dict[str, list[int]] = {name: [0, 0] for name in dataset.setup_names}
    by_session_counts: dict[str, dict[str, dict[str, int]]] = {}

    for ep in all_episodes:
        event, is_last_segment = _next_activation_event(dataset, ep)
        if event is None:
            reason = "dataset_end" if is_last_segment else "segment_end"
            transitions.append(EpisodeTransition(
                from_setup=ep.setup_name, from_episode_start=ep.start_timestamp, from_episode_end=ep.end_timestamp,
                to_activation_event_timestamp=None, to_activated_setups=(), time_to_next_minutes=None,
                censored=True, censor_reason=reason,
            ))
            continue

        time_to_next = (_parse_iso(event.timestamp) - _parse_iso(ep.end_timestamp)).total_seconds() / 60
        transitions.append(EpisodeTransition(
            from_setup=ep.setup_name, from_episode_start=ep.start_timestamp, from_episode_end=ep.end_timestamp,
            to_activation_event_timestamp=event.timestamp, to_activated_setups=event.activated_setups,
            time_to_next_minutes=time_to_next, censored=False, censor_reason=None,
        ))

        same_setup_totals[ep.setup_name][1] += 1
        cross_setup_totals[ep.setup_name][1] += 1
        if ep.setup_name in event.activated_setups:
            same_setup_totals[ep.setup_name][0] += 1
        if any(s != ep.setup_name for s in event.activated_setups):
            cross_setup_totals[ep.setup_name][0] += 1

        session_bucket = by_session_counts.setdefault(ep.session, {name: {} for name in dataset.setup_names})
        for to_setup in event.activated_setups:
            matrix_counts[ep.setup_name][to_setup] = matrix_counts[ep.setup_name].get(to_setup, 0) + 1
            session_bucket[ep.setup_name][to_setup] = session_bucket[ep.setup_name].get(to_setup, 0) + 1

    matrix: list[TransitionMatrixEntry] = []
    for from_setup, row in matrix_counts.items():
        row_total = sum(row.values())
        for to_setup, count in row.items():
            matrix.append(TransitionMatrixEntry(
                from_setup=from_setup, to_setup=to_setup, count=count,
                probability=(count / row_total) if row_total else None,
            ))

    by_session: dict[str, tuple[TransitionMatrixEntry, ...]] = {}
    for session, rows in by_session_counts.items():
        entries = []
        for from_setup, row in rows.items():
            row_total = sum(row.values())
            for to_setup, count in row.items():
                entries.append(TransitionMatrixEntry(
                    from_setup=from_setup, to_setup=to_setup, count=count,
                    probability=(count / row_total) if row_total else None,
                ))
        by_session[session] = tuple(entries)

    same_setup_recurrence_rate = {
        name: (counts[0] / counts[1] if counts[1] else None) for name, counts in same_setup_totals.items()
    }
    cross_setup_recurrence_rate = {
        name: (counts[0] / counts[1] if counts[1] else None) for name, counts in cross_setup_totals.items()
    }

    return SetupTransitions(
        manifest=manifest, transitions=tuple(transitions), matrix=tuple(matrix),
        same_setup_recurrence_rate=same_setup_recurrence_rate,
        cross_setup_recurrence_rate=cross_setup_recurrence_rate, by_session=by_session,
    )

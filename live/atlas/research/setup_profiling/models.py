"""
Sprint RE-2. Data shapes for episode-aware Setup Engine profiling.

RegisteredFactSnapshot/SetupEpisode/ActivationEvent are the structures every
report in this package is built from. Every other dataclass here is one
report's own output shape (RE2_Setup_Profile.md -> SetupProfile,
RE2_Time_Distribution.md -> SetupTimeDistribution, etc.) - kept in this one
module so a report's schema is visible in one place rather than scattered
across service.py.

RunManifest is imported, read-only, from atlas.research.statistical_profiling
.models (RE-1) - approved reuse of a frozen, already-stable metadata shape;
RE-1's package is never modified or moved by this change. This creates a
minor package coupling (RE-2 depends on a sibling research package rather
than a shared base) - disclosed as debt in RE2_Research_Notes.md, not fixed
in this change set.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Optional, Union

from atlas.research.statistical_profiling.models import RunManifest

__all__ = [
    "RunManifest",
    "TerminationReason",
    "RegisteredFactSnapshot",
    "SetupComputabilityRecord",
    "ComputabilityProfile",
    "SetupEpisode",
    "ActivationEvent",
    "NumericStats",
    "SetupDurationStats",
    "SetupProfileEntry",
    "SetupProfile",
    "TimeBucketCount",
    "SetupTimeDistributionEntry",
    "SetupTimeDistribution",
    "InterEpisodeGap",
    "BurstProfile",
    "SetupClusteringEntry",
    "SetupClustering",
    "SetupRelationshipCategory",
    "SetupRelationshipMetadata",
    "OverlapMetrics",
    "ActivationOverlapMetrics",
    "EpisodeIntersectionMetrics",
    "EpisodeContainmentMetrics",
    "ActivationProximityMetrics",
    "SetupOverlapEntry",
    "SetupOverlap",
    "FactContextStats",
    "ContextOffsetProfile",
    "SetupContextProfileEntry",
    "SetupContextProfile",
    "EpisodeTransition",
    "TransitionMatrixEntry",
    "SetupTransitions",
]


def _frozen_mapping(source: Mapping) -> MappingProxyType:
    return MappingProxyType(dict(source))


class TerminationReason(str, Enum):
    """Why an episode's active run stopped being walked - distinct from
    censorship (see SetupEpisode.is_right_censored): BECAME_FALSE is a fully
    observed, non-censored ending; the other three are all right-censoring
    causes, kept as separate reasons because they carry different meaning
    for interpretation (a data-availability gap vs. a real transition to
    False vs. simply running out of dataset)."""

    BECAME_FALSE = "became_false"
    INSUFFICIENT_DATA = "insufficient_data"
    SEGMENT_END = "segment_end"
    DATASET_END = "dataset_end"


@dataclass(frozen=True)
class RegisteredFactSnapshot:
    """A typed, immutable snapshot of the 7 registered Rule Engine facts at
    one bar - replaces an untyped dict for SetupEpisode.start_state/end_state
    and for per-offset context capture. A None field means that specific
    fact was InsufficientData at this bar, never a fabricated value.
    trend_1m/trend_15m/trend_1h are deliberately absent - they are not
    registered Rule Engine facts (see atlas/rule_engine/facts.py's own
    docstring)."""

    volume_spike: Optional[bool]
    displacement: Optional[bool]
    rejection: Optional[bool]
    trend_5m: Optional[str]
    liquidity_sweep: Optional[bool]
    reclaim: Optional[bool]
    vwap_relationship: Optional[str]

    def value_of(self, fact_name: str) -> Optional[Union[bool, str]]:
        return getattr(self, fact_name)


REGISTERED_FACT_NAMES: tuple[str, ...] = (
    "volume_spike", "displacement", "rejection", "trend_5m",
    "liquidity_sweep", "reclaim", "vwap_relationship",
)
BOOLEAN_FACT_NAMES: frozenset[str] = frozenset({
    "volume_spike", "displacement", "rejection", "liquidity_sweep", "reclaim",
})
ENUM_FACT_NAMES: frozenset[str] = frozenset({"trend_5m", "vwap_relationship"})


@dataclass(frozen=True)
class SetupComputabilityRecord:
    """One setup's outcome at one bar, preserved in full - amendment 2's
    "do not reduce the analysis permanently to Optional[bool]" requirement.
    `computable=False` means InsufficientData; `detected` is None exactly
    when computable is False, never a fabricated True/False standing in for
    "unknown"."""

    timestamp: str
    computable: bool
    detected: Optional[bool]
    insufficient_reason: Optional[str]

    def __post_init__(self) -> None:
        if self.computable and self.detected is None:
            raise ValueError("detected must not be None when computable=True")
        if not self.computable and self.detected is not None:
            raise ValueError("detected must be None when computable=False")


@dataclass(frozen=True)
class ComputabilityProfile:
    """Aggregate computability evidence for one setup across the whole
    dataset - the retained, reportable form of every
    SetupComputabilityRecord, so "why wasn't this computable" stays
    debuggable rather than collapsing into a bare bar count."""

    setup_name: str
    total_bars: int
    computable_bars: int
    non_computable_bars: int
    detected_true_bars: int
    detected_false_bars: int
    insufficient_reason_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "insufficient_reason_counts", _frozen_mapping(self.insufficient_reason_counts))


@dataclass(frozen=True)
class SetupEpisode:
    """One contiguous run of detected=True bars for one setup, never
    bridging a segment_by_gap boundary or an InsufficientData position.
    `end_timestamp` is the LAST active bar's timestamp (never the first
    False bar - amendment 1). `segment_id` is the ISO timestamp of the
    segment's first bar (amendment 11 - deterministic, not a transient
    index)."""

    setup_name: str
    segment_id: str
    start_timestamp: str
    end_timestamp: str
    duration_bars: int
    start_state: RegisteredFactSnapshot
    end_state: RegisteredFactSnapshot
    session: str
    hour_ct: str
    weekday_ct: str
    trading_date: str
    termination_reason: TerminationReason
    is_left_censored: bool
    is_right_censored: bool

    @property
    def is_fully_observed(self) -> bool:
        return not self.is_left_censored and not self.is_right_censored


@dataclass(frozen=True)
class ActivationEvent:
    """All setups whose episode STARTS at the exact same timestamp, within
    the same segment - amendment 8's replacement for resolving same-bar
    activations via registry order. `activated_setups` is sorted
    alphabetically for deterministic, reproducible OUTPUT ordering only -
    this is not a claim about which setup "happened first"; no such
    ordering is ever asserted or inferable from this structure."""

    timestamp: str
    segment_id: str
    activated_setups: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "activated_setups", tuple(sorted(self.activated_setups)))


@dataclass(frozen=True)
class NumericStats:
    """Nearest-rank numeric distribution summary - shared shape for both
    episode-duration-in-bars and inter-episode-gap-in-minutes, so the two
    don't need separate types for what is mathematically the same
    computation over different units."""

    count: int
    mean: Optional[float]
    median: Optional[float]
    p75: Optional[float]
    p90: Optional[float]
    p95: Optional[float]
    max: Optional[float]


SetupDurationStats = NumericStats  # explicit alias: bars, not minutes - same shape, distinct name at call sites


@dataclass(frozen=True)
class SetupProfileEntry:
    setup_name: str
    computable_bars: int
    active_bars: int
    active_bar_rate: Optional[float]
    episode_count: int
    all_episodes_duration: SetupDurationStats
    fully_observed_duration: SetupDurationStats
    single_bar_episode_count: int
    multi_bar_episode_count: int
    activation_bar_count: int
    continuation_bar_count: int
    eligible_trading_days: int
    episodes_per_trading_day: Optional[float]
    days_with_activation_count: int
    days_with_activation_rate: Optional[float]
    left_censored_count: int
    right_censored_count: int
    fully_observed_count: int


@dataclass(frozen=True)
class SetupProfile:
    manifest: RunManifest
    entries: tuple[SetupProfileEntry, ...]
    computability: tuple[ComputabilityProfile, ...]


@dataclass(frozen=True)
class TimeBucketCount:
    bucket_key: str
    activation_count: int
    active_bar_count: int
    eligible_bar_count: int
    eligible_trading_days: int
    activation_rate_per_eligible_bar: Optional[float]
    activation_rate_per_trading_day: Optional[float]
    active_bar_rate_per_eligible_bar: Optional[float]


@dataclass(frozen=True)
class SetupTimeDistributionEntry:
    setup_name: str
    by_session: tuple[TimeBucketCount, ...]
    by_hour_ct: tuple[TimeBucketCount, ...]
    by_weekday_ct: tuple[TimeBucketCount, ...]
    by_month: tuple[TimeBucketCount, ...]


@dataclass(frozen=True)
class SetupTimeDistribution:
    manifest: RunManifest
    entries: tuple[SetupTimeDistributionEntry, ...]


@dataclass(frozen=True)
class InterEpisodeGap:
    setup_name: str
    from_episode_end: str
    to_episode_start: str
    gap_minutes: float


@dataclass(frozen=True)
class BurstProfile:
    """A burst is a maximal run of episodes (of the same setup) where every
    consecutive within-segment inter-episode gap is <= threshold_minutes.
    Reported at every threshold in CLUSTER_THRESHOLDS_MINUTES (amendment 9 -
    no single "canonical" threshold is chosen)."""

    threshold_minutes: int
    burst_count: int
    burst_sizes: tuple[int, ...]
    longest_burst_size: int


@dataclass(frozen=True)
class SetupClusteringEntry:
    setup_name: str
    within_segment_gap_count: int
    censored_by_gap_count: int
    gap_minutes_stats: NumericStats
    repeat_within_minutes: Mapping[int, int]
    episodes_per_trading_day: Optional[float]
    bursts: tuple[BurstProfile, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "repeat_within_minutes", _frozen_mapping(self.repeat_within_minutes))


@dataclass(frozen=True)
class SetupClustering:
    manifest: RunManifest
    entries: tuple[SetupClusteringEntry, ...]


class SetupRelationshipCategory(str, Enum):
    """How two setups' relationship is characterized - amendment 5. Sharing
    an input fact is NOT sufficient for LOGICALLY_IMPLIED; that category is
    reserved for pairs where implication is proven from the setup
    definitions for every computable input under the current configuration
    (see relationships.py for the proof for each of the current 6 pairs -
    none currently qualifies, since every real setup so far was
    deliberately built from facts "independent by construction", per each
    setup module's own docstring)."""

    LOGICALLY_IMPLIED = "logically_implied"
    SHARED_INPUTS_ONLY = "shared_inputs_only"
    EMPIRICAL = "empirical"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SetupRelationshipMetadata:
    setup_a: str
    setup_b: str
    category: SetupRelationshipCategory
    rationale: str


@dataclass(frozen=True)
class OverlapMetrics:
    """Concurrent active-bar overlap - both setups computable AND compared
    over the same bar (amendment 4, metric 1)."""

    jointly_computable_bars: int
    p_a_active: Optional[float]
    p_b_active: Optional[float]
    p_both_active: Optional[float]
    lift: Optional[float]
    correlation: Optional[float]
    conditional_p_a_given_b: Optional[float]
    jaccard_active_bars: Optional[float]


@dataclass(frozen=True)
class ActivationOverlapMetrics:
    """Same-bar activation overlap (amendment 4, metric 2) - distinct from
    OverlapMetrics: this counts EPISODE STARTS landing on the identical
    timestamp, not general active-bar co-occurrence."""

    same_bar_activation_count: int
    a_activation_count: int
    b_activation_count: int
    p_same_bar_given_a: Optional[float]
    p_same_bar_given_b: Optional[float]


@dataclass(frozen=True)
class EpisodeIntersectionMetrics:
    """Temporal episode intersection (amendment 4, metric 3) - episode pairs
    whose [start, end] intervals share at least one bar."""

    intersecting_pair_count: int
    a_episode_count: int
    b_episode_count: int
    rate_of_a_episodes_intersecting: Optional[float]
    rate_of_b_episodes_intersecting: Optional[float]


@dataclass(frozen=True)
class EpisodeContainmentMetrics:
    """Full episode containment (amendment 4, metric 4) - one episode's
    interval entirely inside the other's, a strict subset of intersection."""

    a_contained_in_b_count: int
    b_contained_in_a_count: int


@dataclass(frozen=True)
class ActivationProximityMetrics:
    """Activation proximity within a threshold (amendment 4, metric 5) -
    symmetric: counts A-activations with >=1 B-activation within
    +/- threshold_minutes (0 minutes, i.e. the same bar, counts)."""

    threshold_minutes: int
    a_activations_with_nearby_b: int
    b_activations_with_nearby_a: int


@dataclass(frozen=True)
class SetupOverlapEntry:
    setup_a: str
    setup_b: str
    relationship: SetupRelationshipMetadata
    active_bar_overlap: OverlapMetrics
    activation_overlap: ActivationOverlapMetrics
    episode_intersection: EpisodeIntersectionMetrics
    episode_containment: EpisodeContainmentMetrics
    activation_proximity: tuple[ActivationProximityMetrics, ...]


@dataclass(frozen=True)
class SetupOverlap:
    manifest: RunManifest
    entries: tuple[SetupOverlapEntry, ...]


@dataclass(frozen=True)
class FactContextStats:
    """amendment 6: fact computability is FACT-level, tracked independently
    per registered fact at a given offset - never collapsed into a single
    "context available/unavailable" flag for the whole bar."""

    fact_name: str
    bar_available_count: int
    bar_unavailable_count: int
    computable_count: int
    insufficient_count: int
    boolean_true_rate: Optional[float]
    enum_value_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "enum_value_counts", _frozen_mapping(self.enum_value_counts))


@dataclass(frozen=True)
class ContextOffsetProfile:
    """amendment 6: bar-level availability (was the -1/+1/+3 bar even
    inside the same segment) is tracked here at the offset level via
    episode_count vs each FactContextStats.bar_available_count; per-fact
    computability is tracked independently within each FactContextStats."""

    offset_label: str
    episode_count: int
    facts: tuple[FactContextStats, ...]
    session_counts: Mapping[str, int]
    hour_counts: Mapping[str, int]
    weekday_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_counts", _frozen_mapping(self.session_counts))
        object.__setattr__(self, "hour_counts", _frozen_mapping(self.hour_counts))
        object.__setattr__(self, "weekday_counts", _frozen_mapping(self.weekday_counts))


@dataclass(frozen=True)
class SetupContextProfileEntry:
    setup_name: str
    offsets: tuple[ContextOffsetProfile, ...]


@dataclass(frozen=True)
class SetupContextProfile:
    manifest: RunManifest
    entries: tuple[SetupContextProfileEntry, ...]


@dataclass(frozen=True)
class EpisodeTransition:
    """amendment 8: points to the next ActivationEvent (possibly
    multi-label), never to a single next setup chosen by registry order.
    `to_activated_setups` is the (alphabetically sorted for output
    determinism only) tuple of every setup that activated at
    `to_activation_event_timestamp` - a report may expand this multi-label
    event, but must not invent an ordering among its members."""

    from_setup: str
    from_episode_start: str
    from_episode_end: str
    to_activation_event_timestamp: Optional[str]
    to_activated_setups: tuple[str, ...]
    time_to_next_minutes: Optional[float]
    censored: bool
    censor_reason: Optional[str]


@dataclass(frozen=True)
class TransitionMatrixEntry:
    from_setup: str
    to_setup: str
    count: int
    probability: Optional[float]


@dataclass(frozen=True)
class SetupTransitions:
    manifest: RunManifest
    transitions: tuple[EpisodeTransition, ...]
    matrix: tuple[TransitionMatrixEntry, ...]
    same_setup_recurrence_rate: Mapping[str, Optional[float]]
    cross_setup_recurrence_rate: Mapping[str, Optional[float]]
    by_session: Mapping[str, tuple[TransitionMatrixEntry, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "same_setup_recurrence_rate", _frozen_mapping(self.same_setup_recurrence_rate))
        object.__setattr__(self, "cross_setup_recurrence_rate", _frozen_mapping(self.cross_setup_recurrence_rate))
        object.__setattr__(self, "by_session", _frozen_mapping(self.by_session))

"""
Sprint 24B/24C. The profiling package's own domain model - a structural
sibling of atlas.rule_engine.models / atlas.setup_engine.models, one layer
above both: it consumes RuleEngineOutput and SetupEngineOutput (never
MarketState directly for evaluation - only for input filtering/segmentation,
upstream of any fact/setup evaluation) and produces its own separately-owned
report type. Same "never mutate or extend what you consume" discipline every
other layer in this project already applies.

Every type here is observational data only - counts, rates, distributions of
already-computed deterministic outputs. Nothing here computes, scores, or
implies a trading decision, profitability, or signal. See
docs/market_engine/roadmap.md's Sprint 24B/24C entries for the full design
review this package implements.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional

from atlas.core.primitives import Symbol, Timeframe

SCHEMA_VERSION = "1.0"

# Sprint 24C, scope D: the documented, code-confirmed synthetic test symbols
# (docs/market_engine/roadmap.md's "Production test fixtures" section) - no
# repository-level filter for these exists anywhere in atlas/ (confirmed by
# grep), so the profiler carries its own explicit, overrideable denylist
# rather than assuming one exists upstream.
DEFAULT_EXCLUDED_SYMBOLS: frozenset[str] = frozenset({
    "SMOKETEST_NEVER", "SMOKETEST_PARTIAL", "SMOKETEST_FULL",
})


class ProfilingInputError(Exception):
    """Raised when the input MarketState series contains a defect a
    profiling run must never silently paper over - a duplicate or
    non-monotonic occurred_at, or a mix of symbols/timeframes in one series.
    Distinct from an ordinary gap (weekends, holidays, exchange maintenance),
    which is not an error - see segment_by_gap in service.py."""


@dataclass(frozen=True)
class ProfilingRunConfig:
    """Everything one profiling run needs to know before touching a
    repository or evaluating anything - deliberately separate from
    run_metadata (models.RunMetadata) below, which records what actually
    happened, not what was requested.

    `excluded_symbols` and `roll_boundaries` are both explicit and
    overrideable, per Sprint 24B's design review: no synthetic-symbol
    filtering happens anywhere upstream of this config, and no automatic
    contract-roll detection is attempted (see segment_by_gap's own
    docstring for why rolls are never treated as segment boundaries unless
    named here)."""

    symbol: Symbol
    timeframe: Timeframe
    start: datetime
    end: datetime
    limit: int = 10000
    excluded_symbols: frozenset[str] = DEFAULT_EXCLUDED_SYMBOLS
    roll_boundaries: tuple[datetime, ...] = ()


@dataclass(frozen=True)
class ScalarDistribution:
    """min/max/mean/p50/p95 over a scalar evidence field, computed only over
    computable (non-InsufficientData) observations that actually carry the
    field. Percentiles use the nearest-rank method over a sorted ascending
    list: rank = ceil(p / 100 * n), 1-indexed, clamped to [1, n], value =
    sorted_values[rank - 1] - deterministic, dependency-free, and does not
    interpolate between two observed values (every reported percentile is an
    actually-observed value, never a synthesized one)."""

    count: int
    min: Optional[float]
    max: Optional[float]
    mean: Optional[float]
    p50: Optional[float]
    p95: Optional[float]


@dataclass(frozen=True)
class SessionBucketCounts:
    """One bucket's counts within a fact's or setup's session breakdown.
    `positive_count` means true_count for a boolean fact, detected_count for
    a setup, and is None for an enum fact (no single "positive" value - see
    FactProfile.value_kind)."""

    computable_count: int
    positive_count: Optional[int]


@dataclass(frozen=True)
class SessionBreakdown:
    """Compact, count-only breakdown using solely the already-raw, already-
    trusted MarketState fields session_name and is_rth - no derived
    clock-bucket logic (explicitly out of scope this Sprint; the four
    reference-level status facts' own session-boundary semantics remain
    undesigned per rule-fact-inventory.md's "Still unresolved" section, and
    building finer time-of-day bucketing here would be exactly the kind of
    speculative infrastructure that document warns against)."""

    by_session_name: Mapping[str, SessionBucketCounts]
    by_is_rth: Mapping[str, SessionBucketCounts]


@dataclass(frozen=True)
class FactProfile:
    """One registered Rule Engine fact's profile over a run.
    `value_kind` is "boolean" or "enum" - a small, explicit, hand-maintained
    classification (see service.py's BOOLEAN_FACTS/ENUM_FACTS), not inferred
    at runtime from observed values, so a fact that has never fired True
    still reports the correct kind. `firing_rate` is populated only for
    boolean facts; always None for enum facts (no single designated
    "positive" enum value exists for trend_5m or vwap_relationship today -
    per Sprint 24C scope G, inventing one is explicitly out of scope)."""

    fact_name: str
    value_kind: str
    computable_count: int
    insufficient_data_count: int
    value_counts: Mapping[str, int]
    firing_rate: Optional[float]
    evidence_distributions: Mapping[str, ScalarDistribution]
    session_breakdown: SessionBreakdown


@dataclass(frozen=True)
class SetupProfile:
    """One registered Setup Engine setup's profile over a run."""

    setup_name: str
    computable_count: int
    insufficient_data_count: int
    detected_count: int
    not_detected_count: int
    detection_rate: Optional[float]
    session_breakdown: SessionBreakdown


@dataclass(frozen=True)
class HierarchyWindowMetadata:
    """Only meaningful for a configuration-contingent relationship (reclaim
    -> liquidity_sweep) - records the actual window params used in this run
    (read from the real registry's own FactDefinitions, never hardcoded) and
    whether they matched, so a reader never has to assume the relationship's
    precondition held without seeing it confirmed."""

    child_window: int
    parent_window: int
    windows_matched: bool


@dataclass(frozen=True)
class HierarchyRelationshipProfile:
    """One Sprint 24A-documented refinement relationship, checked against
    real profiled data. Raw fact detections are never altered to produce
    this - see service.py's KNOWN_REFINEMENTS for the two entries this
    Sprint reports and rule-fact-inventory.md's "Fact hierarchy within this
    family" for the authoritative proof each entry encodes.

    `held_rate` is None when child_true_count == 0 (undefined, not zero -
    the same null-for-undefined convention every rate in this package
    follows). `discrepancy_count` = child_true_count -
    child_and_parent_true_count; surfaced always, even when zero, never
    hidden. `window_metadata` is populated only for the reclaim relationship
    (config-contingent - see KNOWN_REFINEMENTS); None for the unconditional
    rejection relationship, which needs no window comparison."""

    child_fact: str
    parent_fact: str
    expected_relationship: str
    child_true_count: int
    child_and_parent_true_count: int
    held_rate: Optional[float]
    discrepancy_count: int
    window_metadata: Optional[HierarchyWindowMetadata]


@dataclass(frozen=True)
class SegmentSummary:
    """One strictly-contiguous segment (see service.segment_by_gap) within
    the profiled range. fact_warm_up_observations and
    setup_warm_up_observations are reported SEPARATELY, never combined into
    one ambiguous field, because they differ: the first
    required_history(RULE_ENGINE_REGISTRY) - 1 positions in a segment cannot
    have every Rule Engine fact resolved (trend_5m needs the full 20-bar
    window); the first required_history(SETUP_ENGINE_REGISTRY) - 1 positions
    cannot have every Setup Engine setup resolved. Both counts are purely
    positional - a direct, deterministic consequence of segment length and
    the two registries' own required_history, not inferred from which facts
    actually came back InsufficientData."""

    first_timestamp: str
    last_timestamp: str
    bar_count: int
    fact_warm_up_observations: int
    setup_warm_up_observations: int


@dataclass(frozen=True)
class DataQualitySummary:
    """Everything about the INPUT data's condition for this run - never a
    judgment about whether the market did anything interesting."""

    raw_row_count: int
    excluded_forming_bar_count: int
    excluded_synthetic_symbol_count: int
    segments: tuple[SegmentSummary, ...]
    segment_boundary_count: int
    possible_truncation: bool
    roll_boundaries_configured: tuple[str, ...]
    observations_near_roll_boundary: int


@dataclass(frozen=True)
class RunMetadata:
    """What was actually run, not what was requested (see
    ProfilingRunConfig for the request) - includes enough registry detail
    (names, required_history, and the specific FactDefinition params the
    hierarchy summary depends on) that this report is self-describing
    without a reader needing to separately check the code that produced it."""

    schema_version: str
    symbol: str
    timeframe: str
    requested_start: str
    requested_end: str
    source_row_count: int
    generated_at: str
    rule_engine_fact_names: tuple[str, ...]
    rule_engine_required_history: int
    setup_engine_setup_names: tuple[str, ...]
    setup_engine_required_history: int
    excluded_symbols: tuple[str, ...]
    hierarchy_fact_definitions: Mapping[str, Mapping[str, object]]


@dataclass(frozen=True)
class ProfilingReport:
    """The complete, deterministic (except run_metadata.generated_at - see
    its own field docstring) output of one profiling run."""

    run_metadata: RunMetadata
    data_quality: DataQualitySummary
    fact_metrics: Mapping[str, FactProfile]
    setup_metrics: Mapping[str, SetupProfile]
    setup_co_detection_matrix: Mapping[str, Mapping[str, int]]
    hierarchy_summary: tuple[HierarchyRelationshipProfile, ...]

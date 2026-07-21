"""
Sprint RE-1. Domain model for statistical characterization of Rule Engine
fact outputs. Every type here is observational: counts, rates, run-length
distributions, and association measures over already-computed, already-
deterministic FactOutcome values - nothing here computes, infers, or
implies a forward price outcome, profitability, or trading signal.

`base: FactProfile` on FactStatisticalProfile reuses
atlas.profiling.models.FactProfile unchanged, rather than a second,
overlapping frequency/true-false type - the same "never recompute what
already exists" discipline the rest of this project follows.
"""
from dataclasses import dataclass
from typing import Mapping, Optional

from atlas.profiling.models import FactProfile

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RunManifest:
    """Reproducibility metadata shared by every RE-1 report - what was run,
    against what data, by which code. `code_version` is None only when git
    itself is genuinely unavailable (see
    atlas.research.service.current_code_version), never silently omitted.
    `source_description` names where the input MarketState series actually
    came from (a specific CSV file path today; a repository range query
    once one exists) - the report is self-describing about its own
    provenance without a reader needing to check the run command."""

    schema_version: str
    symbol: str
    timeframe: str
    requested_start: str
    requested_end: str
    source_description: str
    row_count: int
    generated_at: str
    code_version: Optional[str]


@dataclass(frozen=True)
class RunLengthStats:
    """Summary statistics over every consecutive run of one fact holding one
    value - e.g. every run of volume_spike=True. A run never bridges an
    InsufficientData position or a segment boundary (segment_by_gap's own
    contiguity guarantee) - every counted run is a genuinely contiguous
    stretch of computed bars. Empty (zero runs observed) reports
    run_count=0 and every other numeric field None - the same
    null-for-undefined convention atlas.profiling.models.ScalarDistribution
    already established, never zero-as-a-guess."""

    value: str
    run_count: int
    total_bars_in_runs: int
    mean_length: Optional[float]
    median_length: Optional[float]
    p95_length: Optional[float]
    max_length: Optional[int]
    length_histogram: Mapping[int, int]  # run length -> how many runs had exactly that length


@dataclass(frozen=True)
class TransitionMatrix:
    """Counts and probabilities of (from_value -> to_value) over every pair
    of POSITION-CONSECUTIVE, both-computable bars - never bridging an
    InsufficientData gap or a segment boundary, so every counted transition
    is a real, immediately-adjacent state change, not one inferred across a
    period this run has no data for."""

    counts: Mapping[str, Mapping[str, int]]  # from_value -> to_value -> count
    probabilities: Mapping[str, Mapping[str, Optional[float]]]  # from_value -> to_value -> P(to | from)


@dataclass(frozen=True)
class FactStatisticalProfile:
    """One registered fact's complete RE-1 profile - frequency/true-false
    (reused unchanged from atlas.profiling, never recomputed here) plus
    this Sprint's new run-length and transition analysis. `run_length_stats`
    has one entry per value actually observed for this fact (e.g. "true"
    and "false" for a boolean fact that fired at least once each; only
    "false" if it never once fired)."""

    base: FactProfile
    run_length_stats: tuple[RunLengthStats, ...]
    transitions: TransitionMatrix


@dataclass(frozen=True)
class PairwiseRelationship:
    """One unordered pair of facts' co-occurrence statistics, computed only
    over bars where BOTH facts are computable. lift/correlation/
    conditional_dependence are populated only when both facts are boolean
    (see service.BOOLEAN_FACTS) - for any pair involving an enum fact, only
    `category_joint_counts` is reported. This is an explicit scope
    boundary, not a silent gap: lift/correlation/a single conditional-
    dependence delta all presuppose a single "positive" value per fact,
    which no enum fact has (the same reasoning
    atlas.profiling.models.FactProfile.firing_rate already documents for
    why it is None for enum facts)."""

    fact_a: str
    fact_b: str
    jointly_computable_count: int
    both_boolean: bool
    p_a_true: Optional[float]
    p_b_true: Optional[float]
    p_both_true: Optional[float]
    lift: Optional[float]
    correlation: Optional[float]
    conditional_dependence: Optional[float]  # P(A=True | B=True) - P(A=True)
    category_joint_counts: Optional[Mapping[str, Mapping[str, int]]]


@dataclass(frozen=True)
class ConditionalProbabilityEntry:
    """P(target_fact = target_value | condition_fact = condition_value),
    computed only over bars where both facts are computable.
    `condition_sample_size` is the count of such bars where condition_fact
    actually equals condition_value - the denominator `probability` is
    computed from; None when that count is zero (undefined, not zero)."""

    condition_fact: str
    condition_value: str
    target_fact: str
    target_value: str
    probability: Optional[float]
    condition_sample_size: int


@dataclass(frozen=True)
class TimeBucketProfile:
    """One time bucket's (session / hour / weekday) bar count and per-fact
    breakdown - boolean facts report P(True) within the bucket; enum facts
    report a full value-count breakdown (no single "positive" value to
    reduce to a rate, same reasoning as PairwiseRelationship above)."""

    bucket_key: str
    bar_count: int
    boolean_fact_true_rates: Mapping[str, Optional[float]]
    enum_fact_value_counts: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True)
class TimeDistributionProfile:
    """`by_hour_ct`/`by_weekday_ct` use America/Chicago - the same timezone
    convention atlas.monitoring.py already established for this project's
    market-hours logic (CME's home timezone), not a new convention
    introduced here."""

    by_session: tuple[TimeBucketProfile, ...]
    by_hour_ct: tuple[TimeBucketProfile, ...]
    by_weekday_ct: tuple[TimeBucketProfile, ...]


@dataclass(frozen=True)
class StatisticalProfile:
    """The complete RE-1 output - everything the five reports render from."""

    manifest: RunManifest
    fact_profiles: Mapping[str, FactStatisticalProfile]
    pairwise_relationships: tuple[PairwiseRelationship, ...]
    conditional_probabilities: tuple[ConditionalProbabilityEntry, ...]
    time_distribution: TimeDistributionProfile

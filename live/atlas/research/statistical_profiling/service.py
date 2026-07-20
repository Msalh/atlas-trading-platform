"""
Sprint RE-1 (Research Engine Phase 1). Pure statistical characterization of
Rule Engine fact outputs - frequency, run-length/persistence, transitions,
pairwise co-occurrence (lift/correlation/conditional dependence),
conditional probability tables, and time-of-day/session/weekday
distributions.

Explicitly NOT profitability, expectancy, or forward-return analysis:
nothing in this module reads a MarketState past the bar being described,
computes a price change, or produces anything resembling a trading signal.
Every value here is a count, rate, run length, or association measure over
already-computed, already-deterministic FactOutcome values from the Rule
Engine - the same "purely observational" boundary
atlas.profiling.service's own module docstring establishes one layer down,
extended here rather than re-derived.

Reuses, unchanged: atlas.profiling.service.filter_input_states and
.segment_by_gap for input filtering/segmentation (never a second gap-
detection or symbol-denylist implementation), atlas.rule_engine.service
.build_rule_engine_output_window for per-bar fact evaluation (never a
second evaluator), and atlas.profiling.service.profile_market_state_series
for base frequency/true-false numbers (FactProfile) - this module only
adds the run-length/transition/pairwise/conditional/time analyses that
have no existing equivalent anywhere in this codebase.

build_statistical_profile is pure - no repository, no I/O, no wall-clock
read (generated_at is a required parameter, the same determinism rule
profile_market_state_series already follows). This is the property that
makes the pipeline reproducible and reusable unchanged against a much
larger dataset later: only the states/config/source_description passed in
differ, never the code path itself.
"""
import math
from datetime import timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from atlas.market_engine.models import MarketState
from atlas.profiling.models import ProfilingRunConfig
from atlas.profiling.service import filter_input_states, profile_market_state_series, segment_by_gap
from atlas.research.service import current_code_version
from atlas.research.statistical_profiling.models import (
    ConditionalProbabilityEntry,
    FactStatisticalProfile,
    PairwiseRelationship,
    RunLengthStats,
    RunManifest,
    StatisticalProfile,
    TimeBucketProfile,
    TimeDistributionProfile,
    TransitionMatrix,
)
from atlas.rule_engine.models import FactOutcome, FactResult, RuleEngineOutput
from atlas.rule_engine.registry import REGISTRY as RULE_ENGINE_REGISTRY
from atlas.rule_engine.service import build_rule_engine_output_window

SCHEMA_VERSION = "1.0"

# Same explicit, hand-maintained fact-value-shape classification
# atlas.profiling.service.BOOLEAN_FACTS/ENUM_FACTS already establishes -
# duplicated here rather than imported, since atlas.profiling.service's
# copy is module-private-by-convention config for THAT module's own
# FactProfile construction, not a shared public constant; both copies must
# stay in sync with atlas.rule_engine.registry.REGISTRY by hand, the same
# as the original.
BOOLEAN_FACTS: frozenset[str] = frozenset({
    "volume_spike", "displacement", "rejection", "liquidity_sweep", "reclaim",
})
ENUM_FACTS: frozenset[str] = frozenset({"trend_5m", "vwap_relationship"})

_CT = ZoneInfo("America/Chicago")  # same convention atlas.monitoring.py already established
_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _value_key(value: Union[bool, str]) -> str:
    """Same "true"/"false" string convention
    atlas.profiling.service._build_fact_profile already uses for boolean
    values - enum values are already strings and pass through unchanged."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _fact_value_key_sequence(fact_name: str, rule_outputs: list[RuleEngineOutput]) -> list[Optional[str]]:
    """One entry per rule_output, in order; None means InsufficientData at
    that position - never fabricated as a value."""
    keys: list[Optional[str]] = []
    for output in rule_outputs:
        outcome: FactOutcome = output.facts[fact_name]
        keys.append(_value_key(outcome.value) if isinstance(outcome, FactResult) else None)
    return keys


def _runs_within_segment(keys: list[Optional[str]]) -> list[tuple[str, int]]:
    """A run never bridges a None (InsufficientData) position - a None
    always closes any in-progress run without itself becoming one."""
    runs: list[tuple[str, int]] = []
    current_value: Optional[str] = None
    current_length = 0
    for key in keys:
        if key is None:
            if current_value is not None:
                runs.append((current_value, current_length))
            current_value, current_length = None, 0
            continue
        if key == current_value:
            current_length += 1
        else:
            if current_value is not None:
                runs.append((current_value, current_length))
            current_value, current_length = key, 1
    if current_value is not None:
        runs.append((current_value, current_length))
    return runs


def _transitions_within_segment(keys: list[Optional[str]]) -> list[tuple[str, str]]:
    """Only position-CONSECUTIVE, both-computable pairs count - never a
    pair bridging a None (InsufficientData) position."""
    return [(a, b) for a, b in zip(keys, keys[1:]) if a is not None and b is not None]


def _percentile(sorted_values: list[int], p: float) -> float:
    """Nearest-rank percentile - identical method to
    atlas.profiling.service._percentile (that copy is private to this
    module's sibling, and operates on floats not run-length ints; kept as
    a small, separate, equally-simple copy rather than importing a private
    name across package boundaries)."""
    n = len(sorted_values)
    rank = max(1, min(n, math.ceil(p / 100 * n)))
    return sorted_values[rank - 1]


def _build_run_length_stats(value: str, lengths: list[int]) -> RunLengthStats:
    if not lengths:
        return RunLengthStats(
            value=value, run_count=0, total_bars_in_runs=0,
            mean_length=None, median_length=None, p95_length=None, max_length=None,
            length_histogram={},
        )
    ordered = sorted(lengths)
    histogram: dict[int, int] = {}
    for length in lengths:
        histogram[length] = histogram.get(length, 0) + 1
    return RunLengthStats(
        value=value, run_count=len(lengths), total_bars_in_runs=sum(lengths),
        mean_length=sum(lengths) / len(lengths),
        median_length=_percentile(ordered, 50), p95_length=_percentile(ordered, 95),
        max_length=ordered[-1], length_histogram=histogram,
    )


def _build_transition_matrix(possible_values: list[str], pairs: list[tuple[str, str]]) -> TransitionMatrix:
    counts: dict[str, dict[str, int]] = {a: {b: 0 for b in possible_values} for a in possible_values}
    for a, b in pairs:
        counts[a][b] += 1
    probabilities: dict[str, dict[str, Optional[float]]] = {}
    for a in possible_values:
        row_total = sum(counts[a].values())
        probabilities[a] = {b: (counts[a][b] / row_total if row_total > 0 else None) for b in possible_values}
    return TransitionMatrix(counts=counts, probabilities=probabilities)


def _build_fact_statistical_profile(
    fact_name: str, base_profile, segment_rule_outputs: list[list[RuleEngineOutput]],
) -> FactStatisticalProfile:
    all_runs: list[tuple[str, int]] = []
    all_transition_pairs: list[tuple[str, str]] = []
    observed_values: set[str] = set()

    for segment_outputs in segment_rule_outputs:
        keys = _fact_value_key_sequence(fact_name, segment_outputs)
        all_runs.extend(_runs_within_segment(keys))
        all_transition_pairs.extend(_transitions_within_segment(keys))
        observed_values.update(k for k in keys if k is not None)

    lengths_by_value: dict[str, list[int]] = {v: [] for v in observed_values}
    for value, length in all_runs:
        lengths_by_value[value].append(length)

    run_length_stats = tuple(
        _build_run_length_stats(value, lengths_by_value[value]) for value in sorted(observed_values)
    )
    transitions = _build_transition_matrix(sorted(observed_values), all_transition_pairs)
    return FactStatisticalProfile(base=base_profile, run_length_stats=run_length_stats, transitions=transitions)


def _pearson_correlation(xs: list[float], ys: list[float]) -> Optional[float]:
    """None when undefined (fewer than 2 observations, or either series has
    zero variance) - never a fabricated 0.0 standing in for "no
    relationship could be computed"."""
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


def _build_pairwise_relationship(
    fact_a: str, fact_b: str, all_rule_outputs: list[RuleEngineOutput],
) -> PairwiseRelationship:
    both_boolean = fact_a in BOOLEAN_FACTS and fact_b in BOOLEAN_FACTS
    a_outcomes = [output.facts[fact_a] for output in all_rule_outputs]
    b_outcomes = [output.facts[fact_b] for output in all_rule_outputs]
    jointly_computable = [
        (a, b) for a, b in zip(a_outcomes, b_outcomes)
        if isinstance(a, FactResult) and isinstance(b, FactResult)
    ]
    n = len(jointly_computable)

    if not both_boolean:
        category_counts: dict[str, dict[str, int]] = {}
        for a, b in jointly_computable:
            row = category_counts.setdefault(_value_key(a.value), {})
            key_b = _value_key(b.value)
            row[key_b] = row.get(key_b, 0) + 1
        return PairwiseRelationship(
            fact_a=fact_a, fact_b=fact_b, jointly_computable_count=n, both_boolean=False,
            p_a_true=None, p_b_true=None, p_both_true=None, lift=None, correlation=None,
            conditional_dependence=None, category_joint_counts=category_counts,
        )

    if n == 0:
        return PairwiseRelationship(
            fact_a=fact_a, fact_b=fact_b, jointly_computable_count=0, both_boolean=True,
            p_a_true=None, p_b_true=None, p_both_true=None, lift=None, correlation=None,
            conditional_dependence=None, category_joint_counts=None,
        )

    a_true = sum(1 for a, b in jointly_computable if a.value is True)
    b_true = sum(1 for a, b in jointly_computable if b.value is True)
    both_true = sum(1 for a, b in jointly_computable if a.value is True and b.value is True)
    p_a, p_b, p_both = a_true / n, b_true / n, both_true / n

    lift = (p_both / (p_a * p_b)) if p_a > 0 and p_b > 0 else None
    p_a_given_b = (both_true / b_true) if b_true > 0 else None
    conditional_dependence = (p_a_given_b - p_a) if p_a_given_b is not None else None
    correlation = _pearson_correlation(
        [1.0 if a.value is True else 0.0 for a, b in jointly_computable],
        [1.0 if b.value is True else 0.0 for a, b in jointly_computable],
    )

    return PairwiseRelationship(
        fact_a=fact_a, fact_b=fact_b, jointly_computable_count=n, both_boolean=True,
        p_a_true=p_a, p_b_true=p_b, p_both_true=p_both, lift=lift, correlation=correlation,
        conditional_dependence=conditional_dependence, category_joint_counts=None,
    )


def _build_conditional_probabilities(
    fact_names: list[str], all_rule_outputs: list[RuleEngineOutput],
) -> tuple[ConditionalProbabilityEntry, ...]:
    """Exhaustive over every ORDERED pair of distinct facts - P(target |
    condition) for every value either fact was actually observed to take,
    computed only over bars where both are computable."""
    entries: list[ConditionalProbabilityEntry] = []
    for condition_fact in fact_names:
        for target_fact in fact_names:
            if condition_fact == target_fact:
                continue
            condition_outcomes = [output.facts[condition_fact] for output in all_rule_outputs]
            target_outcomes = [output.facts[target_fact] for output in all_rule_outputs]
            jointly_computable = [
                (c, t) for c, t in zip(condition_outcomes, target_outcomes)
                if isinstance(c, FactResult) and isinstance(t, FactResult)
            ]
            if not jointly_computable:
                continue

            condition_values = sorted({_value_key(c.value) for c, _t in jointly_computable})
            target_values = sorted({_value_key(t.value) for _c, t in jointly_computable})

            for condition_value in condition_values:
                subset_targets = [t for c, t in jointly_computable if _value_key(c.value) == condition_value]
                sample_size = len(subset_targets)
                for target_value in target_values:
                    matches = sum(1 for t in subset_targets if _value_key(t.value) == target_value)
                    probability = (matches / sample_size) if sample_size > 0 else None
                    entries.append(ConditionalProbabilityEntry(
                        condition_fact=condition_fact, condition_value=condition_value,
                        target_fact=target_fact, target_value=target_value,
                        probability=probability, condition_sample_size=sample_size,
                    ))
    return tuple(entries)


def _session_key(state: MarketState) -> str:
    return state.session_name.value if state.session_name is not None else "unknown"


def _build_time_bucket_profile(
    bucket_key: str, aligned: list[tuple[MarketState, RuleEngineOutput]], fact_names: list[str],
) -> TimeBucketProfile:
    boolean_rates: dict[str, Optional[float]] = {}
    enum_counts: dict[str, dict[str, int]] = {}
    for fact_name in fact_names:
        computed = [output.facts[fact_name] for _state, output in aligned if isinstance(output.facts[fact_name], FactResult)]
        if fact_name in BOOLEAN_FACTS:
            true_count = sum(1 for outcome in computed if outcome.value is True)
            boolean_rates[fact_name] = (true_count / len(computed)) if computed else None
        else:
            counts: dict[str, int] = {}
            for outcome in computed:
                key = _value_key(outcome.value)
                counts[key] = counts.get(key, 0) + 1
            enum_counts[fact_name] = counts
    return TimeBucketProfile(
        bucket_key=bucket_key, bar_count=len(aligned),
        boolean_fact_true_rates=boolean_rates, enum_fact_value_counts=enum_counts,
    )


def _build_time_distribution(
    aligned: list[tuple[MarketState, RuleEngineOutput]], fact_names: list[str],
) -> TimeDistributionProfile:
    by_session: dict[str, list[tuple[MarketState, RuleEngineOutput]]] = {}
    by_hour: dict[str, list[tuple[MarketState, RuleEngineOutput]]] = {}
    by_weekday: dict[str, list[tuple[MarketState, RuleEngineOutput]]] = {}

    for state, output in aligned:
        by_session.setdefault(_session_key(state), []).append((state, output))
        ct = state.envelope.occurred_at.astimezone(_CT)
        by_hour.setdefault(f"{ct.hour:02d}:00", []).append((state, output))
        by_weekday.setdefault(_WEEKDAY_NAMES[ct.weekday()], []).append((state, output))

    return TimeDistributionProfile(
        by_session=tuple(
            _build_time_bucket_profile(key, by_session[key], fact_names) for key in sorted(by_session)
        ),
        by_hour_ct=tuple(
            _build_time_bucket_profile(key, by_hour[key], fact_names) for key in sorted(by_hour)
        ),
        by_weekday_ct=tuple(
            _build_time_bucket_profile(key, by_weekday[key], fact_names)
            for key in sorted(by_weekday, key=_WEEKDAY_NAMES.index)
        ),
    )


def build_statistical_profile(
    states: list[MarketState], config: ProfilingRunConfig, generated_at, source_description: str,
) -> StatisticalProfile:
    """Pure. See this module's own docstring for the determinism/reuse
    contract. `source_description` is metadata only (e.g. a CSV file path
    today, a repository range description later) - it never alters
    computed values, which is exactly what lets this same function be
    re-pointed at a much larger historical dataset unchanged."""
    filtered, _excluded_forming, _excluded_synthetic = filter_input_states(states, config.excluded_symbols)
    segments = segment_by_gap(filtered)

    segment_rule_outputs = [build_rule_engine_output_window(segment) for segment in segments]
    all_states = [state for segment in segments for state in segment]
    all_rule_outputs = [output for outputs in segment_rule_outputs for output in outputs]
    aligned = list(zip(all_states, all_rule_outputs))

    profiling_report = profile_market_state_series(states, config, generated_at)

    fact_names = [r.name for r in RULE_ENGINE_REGISTRY]
    fact_profiles = {
        name: _build_fact_statistical_profile(name, profiling_report.fact_metrics[name], segment_rule_outputs)
        for name in fact_names
    }

    pairwise = tuple(
        _build_pairwise_relationship(fact_names[i], fact_names[j], all_rule_outputs)
        for i in range(len(fact_names)) for j in range(i + 1, len(fact_names))
    )
    conditional = _build_conditional_probabilities(fact_names, all_rule_outputs)
    time_distribution = _build_time_distribution(aligned, fact_names)

    manifest = RunManifest(
        schema_version=SCHEMA_VERSION,
        symbol=config.symbol.ticker, timeframe=config.timeframe.value,
        requested_start=config.start.isoformat(), requested_end=config.end.isoformat(),
        source_description=source_description, row_count=len(states),
        generated_at=generated_at.astimezone(timezone.utc).isoformat(),
        code_version=current_code_version(),
    )

    return StatisticalProfile(
        manifest=manifest, fact_profiles=fact_profiles,
        pairwise_relationships=pairwise, conditional_probabilities=conditional,
        time_distribution=time_distribution,
    )

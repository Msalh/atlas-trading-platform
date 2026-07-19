"""
Sprint 24B/24C. The profiling package's orchestration - the pipeline
described in Sprint 24C's objective:

    MarketState history -> Rule Engine outputs -> Setup Engine outputs
    -> machine-readable profiling report

Purely observational: every value this module produces is a count, rate, or
distribution over already-computed, already-deterministic Rule Engine/Setup
Engine outputs. Nothing here re-implements a fact or setup predicate, infers
a fact/setup outcome by inspecting raw MarketState, or expresses a trading
signal, confidence score, or profitability claim.

Two entry points, deliberately separated (Sprint 24B's design review, scope
C): profile_market_state_series is pure - no repository, no I/O, no wall
clock - and is what every test in this Sprint calls directly.
profile_market_state_range is the thin, impure repository-backed wrapper
that assembles input via MarketStateRepository.get_range (never the Dataset
Builder export or Replay stream - both are strictly more transformation for
no benefit here) and defaults generated_at to the real wall clock only at
that boundary - never inside the pure function itself. This is the same
domain/impure-adapter split every other pure-core-plus-thin-async-wrapper
pair in this project already follows (build_rule_engine_output vs.
evaluate_latest_rule_engine_output, one layer down).
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.ports import MarketStateRepository
from atlas.profiling.models import (
    DataQualitySummary,
    FactProfile,
    HierarchyRelationshipProfile,
    HierarchyWindowMetadata,
    ProfilingInputError,
    ProfilingReport,
    ProfilingRunConfig,
    RunMetadata,
    ScalarDistribution,
    SegmentSummary,
    SessionBreakdown,
    SessionBucketCounts,
    SetupProfile,
)
from atlas.rule_engine.models import FactOutcome
from atlas.rule_engine.models import FactResult as RuleFactResult
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.registry import REGISTRY as RULE_ENGINE_REGISTRY
from atlas.rule_engine.registry import required_history as rule_engine_required_history
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import SetupEngineOutput, SetupOutcome, SetupResult
from atlas.setup_engine.registry import REGISTRY as SETUP_ENGINE_REGISTRY
from atlas.setup_engine.registry import required_history as setup_engine_required_history
from atlas.setup_engine.service import build_setup_engine_output_window

SCHEMA_VERSION = "1.0"

# Sprint 24C scope G: a small, explicit, hand-maintained classification of
# each registered fact's value shape - NOT inferred at runtime from observed
# values (a fact that has never once fired True must still report the
# correct kind). Kept here, not in models.py, because it is profiler
# behavior/config, not report data.
BOOLEAN_FACTS: frozenset[str] = frozenset({
    "volume_spike", "displacement", "rejection", "liquidity_sweep", "reclaim",
})
ENUM_FACTS: frozenset[str] = frozenset({"trend_5m", "vwap_relationship"})

# Sprint 24C scope G: the exact, explicitly-requested initial scalar evidence
# fields - deliberately not a generic recursive evidence profiler. Each entry
# is (evidence_field_name, is_nested_in_qualifying_levels). Facts not listed
# here (liquidity_sweep, reclaim) have no single evidence scalar this Sprint
# considers useful enough to report - not an oversight, an explicit scope
# limit (Sprint 24C scope G).
SCALAR_EVIDENCE_FIELDS: dict[str, tuple[str, bool]] = {
    "volume_spike": ("volume_ratio", False),
    "displacement": ("range_atr_ratio", False),
    "trend_5m": ("normalized_move", False),
    "vwap_relationship": ("normalized_distance", False),
    "rejection": ("wick_body_ratio", True),
}


@dataclass(frozen=True)
class _KnownRefinement:
    child_fact: str
    parent_fact: str
    expected_relationship: str
    has_window_metadata: bool


# Sprint 24C scope J: the smallest explicit implementation of Sprint 24A's
# Rule Fact Independence Audit findings - exactly two entries, no generic
# graph/hierarchy engine/enum/runtime metadata framework. Each entry's
# authoritative explanation lives in
# docs/market_engine/rule-fact-inventory.md, "Fact hierarchy within this
# family" - this tuple only carries the minimal data needed to check that
# documented claim against real profiled data; it does not restate the proof.
KNOWN_REFINEMENTS: tuple[_KnownRefinement, ...] = (
    _KnownRefinement(
        child_fact="rejection", parent_fact="liquidity_sweep",
        expected_relationship="unconditional whenever both facts are computable",
        has_window_metadata=False,
    ),
    _KnownRefinement(
        child_fact="reclaim", parent_fact="liquidity_sweep",
        expected_relationship="true only under the current matched default window configuration",
        has_window_metadata=True,
    ),
)

# Sprint 24C, no setup-level refinement/supertype pair is reported: neither
# rejection_with_volume_confirmation nor reclaim_with_volume_confirmation is
# a registered Setup Engine setup today (confirmed against SETUP_ENGINE_REGISTRY
# at report-build time, not assumed here) - per scope J, "do not manufacture
# metrics for catalog-only setups." When either is registered, its pair
# belongs here the same way the two fact-level entries above do; nothing about
# this module's structure needs to change to add it.


def _session_key(state: MarketState) -> str:
    return state.session_name.value if state.session_name is not None else "unknown"


def _is_rth_key(state: MarketState) -> str:
    if state.is_rth is None:
        return "unknown"
    return "true" if state.is_rth else "false"


def _empty_bucket() -> dict[str, int]:
    return {"computable": 0, "positive": 0}


def _finalize_session_breakdown(
    by_session: dict[str, dict[str, int]], by_rth: dict[str, dict[str, int]], track_positive: bool,
) -> SessionBreakdown:
    def _finalize(buckets: dict[str, dict[str, int]]) -> dict[str, SessionBucketCounts]:
        return {
            key: SessionBucketCounts(
                computable_count=counts["computable"],
                positive_count=counts["positive"] if track_positive else None,
            )
            for key, counts in buckets.items()
        }
    return SessionBreakdown(by_session_name=_finalize(by_session), by_is_rth=_finalize(by_rth))


def segment_by_gap(states: list[MarketState]) -> list[list[MarketState]]:
    """Pure. Splits an ordered MarketState series into strictly-contiguous
    segments, using exactly the same per-pair cadence check
    atlas.rule_engine.window_integrity.validate_market_state_window applies
    (same variable names, same reasoning) - any interval that would make
    that validator reject a combined window becomes a segment boundary here
    instead of an exception (weekends, holidays, exchange maintenance
    windows, any other missing interval - Sprint 24C scope E). Rows around a
    gap are never excluded, only split into separate segments.

    Duplicate and non-monotonic occurred_at are NOT segment boundaries -
    both raise ProfilingInputError immediately, since both indicate a
    genuine input defect (a repository/ingest bug, not a normal data
    condition) rather than something a profiling run should silently route
    around. Also raises if the input mixes symbols or timeframes - the same
    defense-in-depth check validate_market_state_window applies, run here
    too since this function, unlike that one, is the FIRST integrity check
    an arbitrary caller-supplied series meets.

    Assumes `states` is already filtered (FORMING bars, denylisted symbols
    removed - see _filter_input_states) and sorted ascending by occurred_at;
    does not itself filter or sort."""
    if not states:
        return []

    symbols = {s.symbol.ticker for s in states}
    if len(symbols) > 1:
        raise ProfilingInputError(f"input contains more than one symbol: {sorted(symbols)}")
    timeframes = {s.timeframe for s in states}
    if len(timeframes) > 1:
        raise ProfilingInputError(
            f"input contains more than one timeframe: {sorted(tf.value for tf in timeframes)}"
        )

    expected_minutes = states[0].timeframe.duration_minutes
    segments: list[list[MarketState]] = [[states[0]]]
    for previous, current in zip(states, states[1:]):
        previous_at = previous.envelope.occurred_at
        current_at = current.envelope.occurred_at

        if current_at == previous_at:
            raise ProfilingInputError(f"duplicate occurred_at: {current_at.isoformat()}")
        if current_at < previous_at:
            raise ProfilingInputError(
                f"occurred_at is not strictly increasing: {previous_at.isoformat()} followed by {current_at.isoformat()}"
            )

        actual_minutes = (current_at - previous_at).total_seconds() / 60
        if actual_minutes == expected_minutes:
            segments[-1].append(current)
        else:
            segments.append([current])
    return segments


def _filter_input_states(
    states: list[MarketState], excluded_symbols: frozenset[str],
) -> tuple[list[MarketState], int, int]:
    """Pure. Sprint 24C scope D: excludes rows whose bar_status is not
    CLOSED (a forming bar's derived fields are not final) and rows whose
    symbol is in the denylist, in that order, preserving relative order.
    Returns (kept, excluded_forming_count, excluded_synthetic_count)."""
    excluded_forming = 0
    excluded_synthetic = 0
    kept: list[MarketState] = []
    for state in states:
        if state.bar_status != BarStatus.CLOSED:
            excluded_forming += 1
            continue
        if state.symbol.ticker in excluded_symbols:
            excluded_synthetic += 1
            continue
        kept.append(state)
    return kept, excluded_forming, excluded_synthetic


def _percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile: rank = ceil(p / 100 * n), 1-indexed, clamped
    to [1, n]; returns sorted_values[rank - 1]. Deterministic, dependency-
    free, and never interpolates - every returned value was actually
    observed, never synthesized between two observations."""
    n = len(sorted_values)
    rank = max(1, min(n, math.ceil(p / 100 * n)))
    return sorted_values[rank - 1]


def _scalar_distribution(values: list[float]) -> ScalarDistribution:
    if not values:
        return ScalarDistribution(count=0, min=None, max=None, mean=None, p50=None, p95=None)
    ordered = sorted(values)
    return ScalarDistribution(
        count=len(ordered), min=ordered[0], max=ordered[-1],
        mean=sum(ordered) / len(ordered),
        p50=_percentile(ordered, 50), p95=_percentile(ordered, 95),
    )


def _collect_scalar_values(fact_name: str, outcomes: list[FactOutcome]) -> list[float]:
    config = SCALAR_EVIDENCE_FIELDS.get(fact_name)
    if config is None:
        return []
    field_name, nested = config
    values: list[float] = []
    for outcome in outcomes:
        if not isinstance(outcome, RuleFactResult):
            continue
        if nested:
            for level in outcome.evidence.get("qualifying_levels", []):
                if field_name in level:
                    values.append(level[field_name])
        elif field_name in outcome.evidence:
            values.append(outcome.evidence[field_name])
    return values


def _build_fact_profile(
    fact_name: str, aligned: list[tuple[MarketState, FactOutcome]],
) -> FactProfile:
    is_boolean = fact_name in BOOLEAN_FACTS
    is_enum = fact_name in ENUM_FACTS
    value_kind = "boolean" if is_boolean else "enum" if is_enum else "unknown"

    computable = 0
    insufficient = 0
    value_counts: dict[str, int] = {}
    outcomes: list[FactOutcome] = []
    by_session: dict[str, dict[str, int]] = {}
    by_rth: dict[str, dict[str, int]] = {}

    for state, outcome in aligned:
        outcomes.append(outcome)
        session_bucket = by_session.setdefault(_session_key(state), _empty_bucket())
        rth_bucket = by_rth.setdefault(_is_rth_key(state), _empty_bucket())

        if isinstance(outcome, RuleFactResult):
            computable += 1
            session_bucket["computable"] += 1
            rth_bucket["computable"] += 1
            if is_boolean:
                key = "true" if outcome.value is True else "false"
                value_counts[key] = value_counts.get(key, 0) + 1
                if outcome.value is True:
                    session_bucket["positive"] += 1
                    rth_bucket["positive"] += 1
            else:
                key = str(outcome.value)
                value_counts[key] = value_counts.get(key, 0) + 1
        else:
            insufficient += 1

    firing_rate = None
    if is_boolean and computable > 0:
        firing_rate = value_counts.get("true", 0) / computable

    return FactProfile(
        fact_name=fact_name, value_kind=value_kind,
        computable_count=computable, insufficient_data_count=insufficient,
        value_counts=value_counts, firing_rate=firing_rate,
        evidence_distributions={
            field_name: _scalar_distribution(_collect_scalar_values(fact_name, outcomes))
            for field_name in ([SCALAR_EVIDENCE_FIELDS[fact_name][0]] if fact_name in SCALAR_EVIDENCE_FIELDS else [])
        },
        session_breakdown=_finalize_session_breakdown(by_session, by_rth, track_positive=is_boolean),
    )


def _build_setup_profile(
    setup_name: str, aligned: list[tuple[MarketState, SetupOutcome]],
) -> SetupProfile:
    computable = 0
    insufficient = 0
    detected = 0
    not_detected = 0
    by_session: dict[str, dict[str, int]] = {}
    by_rth: dict[str, dict[str, int]] = {}

    for state, outcome in aligned:
        session_bucket = by_session.setdefault(_session_key(state), _empty_bucket())
        rth_bucket = by_rth.setdefault(_is_rth_key(state), _empty_bucket())

        if isinstance(outcome, SetupResult):
            computable += 1
            session_bucket["computable"] += 1
            rth_bucket["computable"] += 1
            if outcome.detected:
                detected += 1
                session_bucket["positive"] += 1
                rth_bucket["positive"] += 1
            else:
                not_detected += 1
        else:
            insufficient += 1

    detection_rate = detected / computable if computable > 0 else None
    return SetupProfile(
        setup_name=setup_name, computable_count=computable, insufficient_data_count=insufficient,
        detected_count=detected, not_detected_count=not_detected, detection_rate=detection_rate,
        session_breakdown=_finalize_session_breakdown(by_session, by_rth, track_positive=True),
    )


def _build_co_detection_matrix(
    setup_names: list[str], setup_outputs: list[SetupEngineOutput],
) -> dict[str, dict[str, int]]:
    """Complete square matrix, registry order on both axes. Cell(A, B) counts
    observations where both A and B were computable (SetupResult, never
    InsufficientData counted as a false detection) AND both detected=True.
    Diagonal cell(A, A) is therefore exactly A's own detected_count - a
    deliberate choice (Sprint 24C scope I), not null/omitted, tested
    explicitly against SetupProfile.detected_count."""
    matrix: dict[str, dict[str, int]] = {a: {b: 0 for b in setup_names} for a in setup_names}
    for output in setup_outputs:
        by_name = {o.setup_name: o for o in output.setups}
        fired = {name for name in setup_names if isinstance(by_name[name], SetupResult) and by_name[name].detected}
        for a in fired:
            for b in fired:
                matrix[a][b] += 1
    return matrix


def _build_hierarchy_summary(rule_outputs: list[RuleEngineOutput]) -> tuple[HierarchyRelationshipProfile, ...]:
    """Only counts a position toward child_true_count when BOTH the child
    and parent fact are computable at that position - matching Sprint 24A's
    own proof, which is scoped to "whenever both are computable." A position
    where the child is True but the parent is still warming up
    (InsufficientData, e.g. liquidity_sweep needing 3 bars while rejection
    only needs 1) is not a test of the relationship at all and must never be
    counted as a discrepancy - it is excluded from both counters entirely,
    not folded into either one."""
    fact_by_name = {r.name: r for r in RULE_ENGINE_REGISTRY}
    profiles = []
    for refinement in KNOWN_REFINEMENTS:
        child_true = 0
        child_and_parent_true = 0
        for output in rule_outputs:
            child_outcome = output.facts[refinement.child_fact]
            parent_outcome = output.facts[refinement.parent_fact]
            if not isinstance(child_outcome, RuleFactResult) or not isinstance(parent_outcome, RuleFactResult):
                continue
            if child_outcome.value is True:
                child_true += 1
                if parent_outcome.value is True:
                    child_and_parent_true += 1

        held_rate = child_and_parent_true / child_true if child_true > 0 else None
        window_metadata = None
        if refinement.has_window_metadata:
            child_window = fact_by_name[refinement.child_fact].definition.params["window"]
            parent_window = fact_by_name[refinement.parent_fact].definition.params["window"]
            window_metadata = HierarchyWindowMetadata(
                child_window=child_window, parent_window=parent_window,
                windows_matched=child_window == parent_window,
            )

        profiles.append(HierarchyRelationshipProfile(
            child_fact=refinement.child_fact, parent_fact=refinement.parent_fact,
            expected_relationship=refinement.expected_relationship,
            child_true_count=child_true, child_and_parent_true_count=child_and_parent_true,
            held_rate=held_rate, discrepancy_count=child_true - child_and_parent_true,
            window_metadata=window_metadata,
        ))
    return tuple(profiles)


def profile_market_state_series(
    states: list[MarketState], config: ProfilingRunConfig, generated_at: datetime,
) -> ProfilingReport:
    """Pure. The deterministic core of the profiler - no repository, no I/O,
    no wall clock (generated_at is a required parameter precisely so this
    function can never silently reach for datetime.now() - Sprint 24C scope
    M's determinism rule). Every test in this Sprint calls this function
    directly, never profile_market_state_range.

    Pipeline: filter (bar_status, denylisted symbols) -> segment_by_gap
    (raises ProfilingInputError on a duplicate or non-monotonic timestamp,
    splits on any other gap) -> per segment, build_rule_engine_output_window
    then build_setup_engine_output_window -> pool every segment's outputs
    into one run-wide set of metrics. Warm-up observations at the start of
    each segment are never discarded - they are counted as
    InsufficientData, exactly as the two engines themselves already report
    them, and separately tallied per segment (SegmentSummary)."""
    raw_row_count = len(states)
    filtered, excluded_forming, excluded_synthetic = _filter_input_states(states, config.excluded_symbols)
    segments = segment_by_gap(filtered)

    rule_depth = rule_engine_required_history(RULE_ENGINE_REGISTRY)
    setup_depth = setup_engine_required_history(SETUP_ENGINE_REGISTRY)

    all_states: list[MarketState] = []
    all_rule_outputs: list[RuleEngineOutput] = []
    all_setup_outputs: list[SetupEngineOutput] = []
    segment_summaries: list[SegmentSummary] = []

    for segment in segments:
        rule_outputs = build_rule_engine_output_window(segment)
        setup_outputs = build_setup_engine_output_window(rule_outputs, registry=SETUP_ENGINE_REGISTRY)
        all_states.extend(segment)
        all_rule_outputs.extend(rule_outputs)
        all_setup_outputs.extend(setup_outputs)
        segment_summaries.append(SegmentSummary(
            first_timestamp=segment[0].envelope.occurred_at.isoformat(),
            last_timestamp=segment[-1].envelope.occurred_at.isoformat(),
            bar_count=len(segment),
            fact_warm_up_observations=min(len(segment), max(0, rule_depth - 1)),
            setup_warm_up_observations=min(len(segment), max(0, setup_depth - 1)),
        ))

    fact_names = [r.name for r in RULE_ENGINE_REGISTRY]
    fact_metrics = {
        name: _build_fact_profile(
            name, [(state, output.facts[name]) for state, output in zip(all_states, all_rule_outputs)],
        )
        for name in fact_names
    }

    setup_names = [r.name for r in SETUP_ENGINE_REGISTRY]
    setup_by_name_per_output = [{o.setup_name: o for o in output.setups} for output in all_setup_outputs]
    setup_metrics = {
        name: _build_setup_profile(
            name,
            [(state, by_name[name]) for state, by_name in zip(all_states, setup_by_name_per_output)],
        )
        for name in setup_names
    }

    co_detection_matrix = _build_co_detection_matrix(setup_names, all_setup_outputs)
    hierarchy_summary = _build_hierarchy_summary(all_rule_outputs)

    observations_near_roll = 0
    if config.roll_boundaries:
        roll_set_minutes = {(b.year, b.month, b.day, b.hour, b.minute) for b in config.roll_boundaries}
        for state in all_states:
            at = state.envelope.occurred_at
            if (at.year, at.month, at.day, at.hour, at.minute) in roll_set_minutes:
                observations_near_roll += 1

    fact_by_name = {r.name: r for r in RULE_ENGINE_REGISTRY}
    hierarchy_fact_definitions = {
        refinement.child_fact: dict(fact_by_name[refinement.child_fact].definition.params)
        for refinement in KNOWN_REFINEMENTS
    } | {
        refinement.parent_fact: dict(fact_by_name[refinement.parent_fact].definition.params)
        for refinement in KNOWN_REFINEMENTS
    }

    run_metadata = RunMetadata(
        schema_version=SCHEMA_VERSION,
        symbol=config.symbol.ticker, timeframe=config.timeframe.value,
        requested_start=config.start.isoformat(), requested_end=config.end.isoformat(),
        source_row_count=raw_row_count, generated_at=generated_at.astimezone(timezone.utc).isoformat(),
        rule_engine_fact_names=tuple(fact_names), rule_engine_required_history=rule_depth,
        setup_engine_setup_names=tuple(setup_names), setup_engine_required_history=setup_depth,
        excluded_symbols=tuple(sorted(config.excluded_symbols)),
        hierarchy_fact_definitions=hierarchy_fact_definitions,
    )

    data_quality = DataQualitySummary(
        raw_row_count=raw_row_count,
        excluded_forming_bar_count=excluded_forming,
        excluded_synthetic_symbol_count=excluded_synthetic,
        segments=tuple(segment_summaries),
        segment_boundary_count=max(0, len(segments) - 1),
        possible_truncation=raw_row_count == config.limit,
        roll_boundaries_configured=tuple(b.isoformat() for b in config.roll_boundaries),
        observations_near_roll_boundary=observations_near_roll,
    )

    return ProfilingReport(
        run_metadata=run_metadata, data_quality=data_quality,
        fact_metrics=fact_metrics, setup_metrics=setup_metrics,
        setup_co_detection_matrix=co_detection_matrix, hierarchy_summary=hierarchy_summary,
    )


async def profile_market_state_range(
    repository: MarketStateRepository, config: ProfilingRunConfig, generated_at: Optional[datetime] = None,
) -> ProfilingReport:
    """The one impure entry point - assembles input via
    MarketStateRepository.get_range directly (Sprint 24C scope C: not the
    Dataset Builder export, which serializes to JSON-safe dicts and would
    have to be re-parsed back into MarketState for no benefit; not the
    Replay Engine stream, which wraps the exact same get_range call in an
    async generator for no benefit in a bounded historical run). get_range
    already returns ordered MarketState domain objects in the type and order
    this pipeline needs - zero transformation in between.

    generated_at defaults to the real wall clock ONLY here, at the impure
    boundary - profile_market_state_series itself never touches
    datetime.now(). Every test that needs deterministic output calls
    profile_market_state_series directly with an injected value instead of
    this wrapper."""
    states = await repository.get_range(config.symbol, config.timeframe, config.start, config.end, config.limit)
    resolved_generated_at = generated_at if generated_at is not None else datetime.now(timezone.utc)
    return profile_market_state_series(list(states), config, resolved_generated_at)

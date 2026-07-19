"""
Sprint 24C. Tests for atlas.profiling - the historical fact/setup profiler.

Per this Sprint's explicit test restriction: no test here constructs an
"impossible" production MarketState fixture (e.g. rejection=True with
liquidity_sweep=False) through the real evaluators, and no test monkeypatches
or weakens a production evaluator to manufacture one. Where a discrepancy
needs to be exercised (TestHierarchySummary), the aggregation function is
called directly with hand-built RuleEngineOutput/FactResult objects instead -
see that class's own docstring.
"""
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository
from atlas.profiling.models import ProfilingInputError, ProfilingRunConfig
from atlas.profiling.serialization import profiling_report_to_dict
from atlas.profiling.service import (
    KNOWN_REFINEMENTS,
    _build_co_detection_matrix,
    _build_fact_profile,
    _build_hierarchy_summary,
    _build_setup_profile,
    _filter_input_states,
    _percentile,
    _scalar_distribution,
    profile_market_state_range,
    profile_market_state_series,
    segment_by_gap,
)
from atlas.rule_engine.models import FactResult as RuleFactResult
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.registry import REGISTRY as RULE_ENGINE_REGISTRY
from atlas.setup_engine.models import InsufficientData as SetupInsufficientData
from atlas.setup_engine.models import SetupEngineOutput, SetupResult, Severity
from atlas.setup_engine.registry import REGISTRY as SETUP_ENGINE_REGISTRY

FIXED_GENERATED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def _state(event_id="e1", occurred_at="2026-07-18T13:00:00", **overrides):
    fields = dict(
        envelope=Event(
            event_type="bar_closed", source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc), event_id=event_id,
        ),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
    )
    fields.update(overrides)
    return MarketState(**fields)


def _series(count, base="2026-07-18T13:00:00", cadence_minutes=5, **shared_overrides):
    """A fully-computable ascending series: every single-bar fact
    (volume_spike, displacement, rejection, vwap_relationship) can compute
    from bar 0; liquidity_sweep/reclaim from bar 2 (3-bar window);
    trend_5m only once a full 20-bar lookback exists. previous_day_high is
    set far above every bar's own high so rejection/liquidity_sweep never
    spuriously qualify unless a test deliberately engineers that."""
    base_dt = datetime.fromisoformat(base)
    fields = dict(
        open=Price(100.0, 0.25), high=Price(110.0, 0.25), low=Price(90.0, 0.25),
        atr=10.0, volume_ratio=1.0, distance_from_vwap_points=3.0,
        previous_day_high=Price(1000.0, 0.25),
    )
    fields.update(shared_overrides)
    states = []
    for i in range(count):
        bar_fields = dict(fields)
        bar_fields.setdefault("close", Price(100.0 + i * 0.25, 0.25))
        states.append(_state(
            event_id=f"e{i}", occurred_at=(base_dt + timedelta(minutes=cadence_minutes * i)).isoformat(),
            **bar_fields,
        ))
    return states


def _config(symbol="MNQU6", start="2026-07-18T00:00:00", end="2026-07-19T00:00:00", **overrides):
    fields = dict(
        symbol=Symbol(symbol), timeframe=Timeframe.M5,
        start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
        end=datetime.fromisoformat(end).replace(tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return ProfilingRunConfig(**fields)


class TestSegmentByGap:
    def test_empty_input(self):
        assert segment_by_gap([]) == []

    def test_contiguous_series_is_one_segment(self):
        states = _series(5)
        assert segment_by_gap(states) == [states]

    def test_a_gap_splits_into_two_segments(self):
        states = _series(3)
        # A weekend-sized jump between bar 2 and bar 3.
        states.append(_state(
            event_id="e3", occurred_at="2026-07-21T13:00:00",
            open=Price(100.0, 0.25), high=Price(110.0, 0.25), low=Price(90.0, 0.25), close=Price(101.0, 0.25),
        ))
        segments = segment_by_gap(states)
        assert len(segments) == 2
        assert segments[0] == states[:3]
        assert segments[1] == states[3:]

    def test_multiple_gaps_split_into_multiple_segments(self):
        a = _series(2, base="2026-07-18T13:00:00")
        b = _series(2, base="2026-07-19T13:00:00")
        c = _series(2, base="2026-07-20T13:00:00")
        segments = segment_by_gap(a + b + c)
        assert [len(s) for s in segments] == [2, 2, 2]

    def test_duplicate_timestamp_raises(self):
        states = _series(2)
        states[1] = _state(event_id="dup", occurred_at=states[0].envelope.occurred_at.isoformat())
        with pytest.raises(ProfilingInputError, match="duplicate"):
            segment_by_gap(states)

    def test_non_monotonic_timestamp_raises(self):
        states = _series(3)
        states[1], states[2] = states[2], states[1]
        with pytest.raises(ProfilingInputError, match="not strictly increasing"):
            segment_by_gap(states)

    def test_mixed_symbol_raises(self):
        states = _series(2)
        states[1] = _state(event_id="other", occurred_at="2026-07-18T13:05:00", symbol=Symbol("ESU6"))
        with pytest.raises(ProfilingInputError, match="more than one symbol"):
            segment_by_gap(states)

    def test_mixed_timeframe_raises(self):
        states = _series(2)
        states[1] = _state(event_id="other", occurred_at="2026-07-18T13:05:00", timeframe=Timeframe.M1)
        with pytest.raises(ProfilingInputError, match="more than one timeframe"):
            segment_by_gap(states)


class TestInputFiltering:
    def test_excludes_forming_bars(self):
        states = _series(3)
        states[1] = _state(event_id="forming", occurred_at=states[1].envelope.occurred_at.isoformat(), bar_status=BarStatus.FORMING)
        kept, excluded_forming, excluded_synthetic = _filter_input_states(states, frozenset())
        assert len(kept) == 2
        assert excluded_forming == 1
        assert excluded_synthetic == 0

    def test_excludes_default_smoketest_symbols(self):
        states = _series(2)
        states[1] = _state(event_id="smoke", occurred_at=states[1].envelope.occurred_at.isoformat(), symbol=Symbol("SMOKETEST_FULL"))
        kept, excluded_forming, excluded_synthetic = _filter_input_states(
            states, frozenset({"SMOKETEST_NEVER", "SMOKETEST_PARTIAL", "SMOKETEST_FULL"}),
        )
        assert len(kept) == 1
        assert excluded_synthetic == 1

    def test_denylist_is_overrideable(self):
        states = _series(2)
        kept, _, excluded_synthetic = _filter_input_states(states, frozenset({"MNQU6"}))
        assert len(kept) == 0
        assert excluded_synthetic == 2

    def test_preserves_relative_order(self):
        states = _series(4)
        kept, _, _ = _filter_input_states(states, frozenset())
        assert kept == states


class TestPercentileAndScalarDistribution:
    def test_percentile_nearest_rank(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert _percentile(values, 50) == 30.0
        assert _percentile(values, 95) == 50.0
        assert _percentile(values, 1) == 10.0

    def test_empty_distribution(self):
        d = _scalar_distribution([])
        assert d.count == 0
        assert d.min is None and d.max is None and d.mean is None and d.p50 is None and d.p95 is None

    def test_single_value_distribution(self):
        d = _scalar_distribution([7.5])
        assert d.count == 1
        assert d.min == d.max == d.mean == d.p50 == d.p95 == 7.5

    def test_distribution_uses_sorted_order_regardless_of_input_order(self):
        d = _scalar_distribution([30.0, 10.0, 20.0])
        assert d.min == 10.0 and d.max == 30.0 and d.mean == 20.0


class TestFactProfileAggregation:
    def _rule_output(self, occurred_at, **facts):
        return RuleEngineOutput(schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at, facts=facts)

    def test_boolean_fact_aggregation_and_firing_rate(self):
        states = [_state(event_id=f"e{i}") for i in range(4)]
        aligned = [
            (states[0], RuleFactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={"volume_ratio": 2.0})),
            (states[1], RuleFactResult(fact_name="volume_spike", definition_version="1.0", value=False, evidence={"volume_ratio": 1.0})),
            (states[2], RuleFactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={"volume_ratio": 3.0})),
            (states[3], FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason="missing")),
        ]
        profile = _build_fact_profile("volume_spike", aligned)
        assert profile.value_kind == "boolean"
        assert profile.computable_count == 3
        assert profile.insufficient_data_count == 1
        assert profile.value_counts == {"true": 2, "false": 1}
        assert profile.firing_rate == pytest.approx(2 / 3)
        assert profile.evidence_distributions["volume_ratio"].count == 3

    def test_enum_fact_aggregation_no_firing_rate(self):
        states = [_state(event_id=f"e{i}") for i in range(3)]
        aligned = [
            (states[0], RuleFactResult(fact_name="trend_5m", definition_version="1.0", value="up", evidence={})),
            (states[1], RuleFactResult(fact_name="trend_5m", definition_version="1.0", value="up", evidence={})),
            (states[2], RuleFactResult(fact_name="trend_5m", definition_version="1.0", value="flat", evidence={})),
        ]
        profile = _build_fact_profile("trend_5m", aligned)
        assert profile.value_kind == "enum"
        assert profile.value_counts == {"up": 2, "flat": 1}
        assert profile.firing_rate is None

    def test_null_firing_rate_when_zero_computable(self):
        states = [_state(event_id="e0")]
        aligned = [(states[0], FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason="missing"))]
        profile = _build_fact_profile("volume_spike", aligned)
        assert profile.computable_count == 0
        assert profile.firing_rate is None

    def test_rejection_scalar_distribution_collects_nested_qualifying_levels(self):
        states = [_state(event_id="e0")]
        evidence = {
            "tick_size": 0.25, "threshold": 2.0,
            "qualifying_levels": [
                {"reference_level": "previous_day_high", "wick_body_ratio": 3.0},
                {"reference_level": "overnight_high", "wick_body_ratio": 5.0},
            ],
        }
        aligned = [(states[0], RuleFactResult(fact_name="rejection", definition_version="1.0", value=True, evidence=evidence))]
        profile = _build_fact_profile("rejection", aligned)
        assert profile.evidence_distributions["wick_body_ratio"].count == 2
        assert profile.evidence_distributions["wick_body_ratio"].min == 3.0
        assert profile.evidence_distributions["wick_body_ratio"].max == 5.0

    def test_session_breakdown_groups_by_session_name_and_is_rth(self):
        from atlas.core.primitives import Session
        rth_state = _state(event_id="e0", session_name=Session.RTH, is_rth=True)
        onc_state = _state(event_id="e1", occurred_at="2026-07-18T13:05:00", session_name=Session.OVERNIGHT, is_rth=False)
        aligned = [
            (rth_state, RuleFactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={})),
            (onc_state, RuleFactResult(fact_name="volume_spike", definition_version="1.0", value=False, evidence={})),
        ]
        profile = _build_fact_profile("volume_spike", aligned)
        assert profile.session_breakdown.by_session_name["RTH"].computable_count == 1
        assert profile.session_breakdown.by_session_name["RTH"].positive_count == 1
        assert profile.session_breakdown.by_is_rth["false"].computable_count == 1
        assert profile.session_breakdown.by_is_rth["false"].positive_count == 0


class TestSetupProfileAggregation:
    def _fact(self):
        from atlas.setup_engine.models import SetupEvidence
        return SetupEvidence(supporting_facts=())

    def test_detection_aggregation_and_rate(self):
        states = [_state(event_id=f"e{i}") for i in range(3)]
        aligned = [
            (states[0], SetupResult(setup_name="x", definition_version="1.0", detected=True, severity=Severity.NORMAL, evidence=self._fact())),
            (states[1], SetupResult(setup_name="x", definition_version="1.0", detected=False, severity=None, evidence=self._fact())),
            (states[2], SetupInsufficientData(setup_name="x", definition_version="1.0", reason="missing")),
        ]
        profile = _build_setup_profile("x", aligned)
        assert profile.computable_count == 2
        assert profile.insufficient_data_count == 1
        assert profile.detected_count == 1
        assert profile.not_detected_count == 1
        assert profile.detection_rate == pytest.approx(0.5)

    def test_null_detection_rate_when_zero_computable(self):
        states = [_state(event_id="e0")]
        aligned = [(states[0], SetupInsufficientData(setup_name="x", definition_version="1.0", reason="missing"))]
        profile = _build_setup_profile("x", aligned)
        assert profile.detection_rate is None


class TestCoDetectionMatrix:
    def _output(self, occurred_at, **outcomes):
        setups = tuple(outcomes[name] for name in outcomes)
        return SetupEngineOutput(schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at, setups=setups)

    def _result(self, name, detected):
        from atlas.setup_engine.models import SetupEvidence
        return SetupResult(
            setup_name=name, definition_version="1.0", detected=detected,
            severity=Severity.NORMAL if detected else None, evidence=SetupEvidence(supporting_facts=()),
        )

    def test_complete_square_matrix_with_zero_cells_present(self):
        outputs = [self._output("t0", a=self._result("a", True), b=self._result("b", False))]
        matrix = _build_co_detection_matrix(["a", "b"], outputs)
        assert matrix == {"a": {"a": 1, "b": 0}, "b": {"a": 0, "b": 0}}

    def test_diagonal_equals_own_detected_count(self):
        outputs = [
            self._output("t0", a=self._result("a", True), b=self._result("b", True)),
            self._output("t1", a=self._result("a", True), b=self._result("b", False)),
            self._output("t2", a=self._result("a", False), b=self._result("b", False)),
        ]
        matrix = _build_co_detection_matrix(["a", "b"], outputs)
        assert matrix["a"]["a"] == 2
        assert matrix["b"]["b"] == 1
        assert matrix["a"]["b"] == matrix["b"]["a"] == 1

    def test_insufficient_data_never_counted_as_co_detection(self):
        outputs = [self._output(
            "t0", a=self._result("a", True),
            b=SetupInsufficientData(setup_name="b", definition_version="1.0", reason="missing"),
        )]
        matrix = _build_co_detection_matrix(["a", "b"], outputs)
        assert matrix["a"]["b"] == 0
        assert matrix["a"]["a"] == 1


class TestHierarchySummary:
    """Sprint 24C's explicit test restriction: no impossible production
    fixture through real evaluators, no monkeypatching. Discrepancy
    reporting is tested by calling _build_hierarchy_summary directly with
    hand-built RuleEngineOutput/FactResult objects - real evaluators never
    run in that test."""

    def _output(self, occurred_at, rejection=None, liquidity_sweep=None, reclaim=None):
        facts = {}
        for name, value in (("rejection", rejection), ("liquidity_sweep", liquidity_sweep), ("reclaim", reclaim)):
            if value is None:
                facts[name] = FactInsufficientData(fact_name=name, definition_version="1.0", reason="synthetic")
            else:
                facts[name] = RuleFactResult(fact_name=name, definition_version="1.0", value=value, evidence={})
        return RuleEngineOutput(schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at, facts=facts)

    def test_held_rate_is_1_when_relationship_holds(self):
        outputs = [
            self._output("t0", rejection=True, liquidity_sweep=True, reclaim=False),
            self._output("t1", rejection=False, liquidity_sweep=False, reclaim=False),
        ]
        profiles = {p.child_fact: p for p in _build_hierarchy_summary(outputs)}
        rejection_profile = profiles["rejection"]
        assert rejection_profile.child_true_count == 1
        assert rejection_profile.child_and_parent_true_count == 1
        assert rejection_profile.held_rate == 1.0
        assert rejection_profile.discrepancy_count == 0

    def test_discrepancy_is_surfaced_never_hidden(self):
        # Synthetic-only: rejection=True with liquidity_sweep=False is not
        # reachable via the real evaluators (Sprint 24A's proof) - built by
        # hand here specifically to prove the profiler reports the
        # discrepancy rather than silently correcting or hiding it.
        outputs = [self._output("t0", rejection=True, liquidity_sweep=False, reclaim=False)]
        profiles = {p.child_fact: p for p in _build_hierarchy_summary(outputs)}
        rejection_profile = profiles["rejection"]
        assert rejection_profile.child_true_count == 1
        assert rejection_profile.child_and_parent_true_count == 0
        assert rejection_profile.held_rate == 0.0
        assert rejection_profile.discrepancy_count == 1

    def test_held_rate_null_when_child_never_true(self):
        outputs = [self._output("t0", rejection=False, liquidity_sweep=False, reclaim=False)]
        profiles = {p.child_fact: p for p in _build_hierarchy_summary(outputs)}
        assert profiles["rejection"].child_true_count == 0
        assert profiles["rejection"].held_rate is None

    def test_warm_up_insufficient_data_excluded_from_both_counters(self):
        # Rejection computable+True, liquidity_sweep still InsufficientData
        # (warm-up) - must not count toward child_true_count at all, since
        # the relationship was never actually tested at this position.
        outputs = [self._output("t0", rejection=True, liquidity_sweep=None, reclaim=False)]
        profiles = {p.child_fact: p for p in _build_hierarchy_summary(outputs)}
        assert profiles["rejection"].child_true_count == 0

    def test_reclaim_window_metadata_reflects_real_registry(self):
        outputs = [self._output("t0", rejection=False, liquidity_sweep=False, reclaim=False)]
        profiles = {p.child_fact: p for p in _build_hierarchy_summary(outputs)}
        reclaim_profile = profiles["reclaim"]
        assert reclaim_profile.window_metadata is not None
        assert reclaim_profile.window_metadata.child_window == 3
        assert reclaim_profile.window_metadata.parent_window == 3
        assert reclaim_profile.window_metadata.windows_matched is True
        assert profiles["rejection"].window_metadata is None

    def test_exactly_two_known_refinements(self):
        assert len(KNOWN_REFINEMENTS) == 2
        assert {(r.child_fact, r.parent_fact) for r in KNOWN_REFINEMENTS} == {
            ("rejection", "liquidity_sweep"), ("reclaim", "liquidity_sweep"),
        }


class TestRequiredHistoryBoundary:
    """Sprint 24C scope N: 20 bars produce exactly one fully-computed
    RuleEngineOutput (trend_5m needs the full 20-bar lookback); 21 bars
    produce exactly two. Both derived from real production orchestration,
    not asserted from documentation."""

    def test_20_bars_yields_exactly_one_fully_computed_trend_5m(self):
        states = _series(20)
        report = profile_market_state_series(states, _config(), FIXED_GENERATED_AT)
        assert report.fact_metrics["trend_5m"].computable_count == 1
        assert report.fact_metrics["trend_5m"].insufficient_data_count == 19
        assert report.data_quality.segments[0].fact_warm_up_observations == 19

    def test_21_bars_yields_exactly_two_fully_computed_trend_5m(self):
        states = _series(21)
        report = profile_market_state_series(states, _config(), FIXED_GENERATED_AT)
        assert report.fact_metrics["trend_5m"].computable_count == 2
        assert report.fact_metrics["trend_5m"].insufficient_data_count == 19

    def test_setup_engine_completeness_needs_far_fewer_bars(self):
        # required_history(SETUP_ENGINE_REGISTRY) == 2, driven by
        # sustained_displacement_streak needing displacement (single-bar) on
        # 2 consecutive outputs - no registered setup consumes trend_5m, so
        # setup-level completeness does not wait for the 20-bar fact warm-up.
        states = _series(2)
        report = profile_market_state_series(states, _config(), FIXED_GENERATED_AT)
        assert report.setup_metrics["sustained_displacement_streak"].computable_count == 1
        assert report.data_quality.segments[0].setup_warm_up_observations == 1


class TestInsufficientDataAccountingInvariant:
    def test_computable_plus_insufficient_equals_total_for_every_fact_and_setup(self):
        states = _series(5)
        report = profile_market_state_series(states, _config(), FIXED_GENERATED_AT)
        for fact_profile in report.fact_metrics.values():
            assert fact_profile.computable_count + fact_profile.insufficient_data_count == 5
        for setup_profile in report.setup_metrics.values():
            assert setup_profile.computable_count + setup_profile.insufficient_data_count == 5


class TestProfileMarketStateSeriesEndToEnd:
    def test_deterministic_repeatability_with_injected_generated_at(self):
        states = _series(5)
        config = _config()
        report_a = profiling_report_to_dict(profile_market_state_series(states, config, FIXED_GENERATED_AT))
        report_b = profiling_report_to_dict(profile_market_state_series(states, config, FIXED_GENERATED_AT))
        assert report_a == report_b

    def test_registry_order_preserved_in_fact_and_setup_metrics(self):
        report = profile_market_state_series(_series(3), _config(), FIXED_GENERATED_AT)
        assert list(report.fact_metrics.keys()) == [r.name for r in RULE_ENGINE_REGISTRY]
        assert list(report.setup_metrics.keys()) == [r.name for r in SETUP_ENGINE_REGISTRY]

    def test_gap_produces_two_segments_in_data_quality(self):
        a = _series(3, base="2026-07-18T13:00:00")
        b = _series(3, base="2026-07-19T13:00:00")
        report = profile_market_state_series(a + b, _config(), FIXED_GENERATED_AT)
        assert len(report.data_quality.segments) == 2
        assert report.data_quality.segment_boundary_count == 1

    def test_duplicate_timestamp_fails_the_run(self):
        states = _series(3)
        states[1] = _state(event_id="dup", occurred_at=states[0].envelope.occurred_at.isoformat())
        with pytest.raises(ProfilingInputError):
            profile_market_state_series(states, _config(), FIXED_GENERATED_AT)

    def test_forming_and_smoketest_rows_excluded_end_to_end(self):
        states = _series(3)
        states.append(_state(event_id="forming", occurred_at="2026-07-18T13:15:00", bar_status=BarStatus.FORMING))
        states.append(_state(event_id="smoke", occurred_at="2026-07-18T13:20:00", symbol=Symbol("SMOKETEST_FULL")))
        report = profile_market_state_series(states, _config(), FIXED_GENERATED_AT)
        assert report.data_quality.raw_row_count == 5
        assert report.data_quality.excluded_forming_bar_count == 1
        assert report.data_quality.excluded_synthetic_symbol_count == 1
        assert sum(s.bar_count for s in report.data_quality.segments) == 3

    def test_possible_truncation_flag(self):
        states = _series(3)
        report = profile_market_state_series(states, _config(limit=3), FIXED_GENERATED_AT)
        assert report.data_quality.possible_truncation is True
        report_not_truncated = profile_market_state_series(states, _config(limit=100), FIXED_GENERATED_AT)
        assert report_not_truncated.data_quality.possible_truncation is False

    def test_roll_boundary_disclosed_not_removed(self):
        states = _series(3)
        roll_at = states[1].envelope.occurred_at
        config = _config(roll_boundaries=(roll_at,))
        report = profile_market_state_series(states, config, FIXED_GENERATED_AT)
        assert report.data_quality.observations_near_roll_boundary == 1
        assert report.data_quality.raw_row_count == 3
        assert sum(s.bar_count for s in report.data_quality.segments) == 3

    def test_no_registered_setups_consume_trend_5m_so_hierarchy_and_setup_metrics_are_independent(self):
        # Sanity check on Sprint 24C scope J: only fact-level hierarchy
        # entries are produced (no setup-level refinement pair exists in the
        # current registry) - the hierarchy_summary length is fixed at 2.
        report = profile_market_state_series(_series(3), _config(), FIXED_GENERATED_AT)
        assert len(report.hierarchy_summary) == 2


class TestRepositoryWrapper:
    @pytest.mark.asyncio
    async def test_profile_market_state_range_uses_get_range_directly(self):
        repository = InMemoryMarketStateRepository()
        for state in _series(3):
            await repository.ingest(state, raw_payload="{}")
        config = _config()
        report = await profile_market_state_range(repository, config, generated_at=FIXED_GENERATED_AT)
        assert report.data_quality.raw_row_count == 3
        assert report.run_metadata.generated_at == FIXED_GENERATED_AT.isoformat()

    @pytest.mark.asyncio
    async def test_generated_at_defaults_to_wall_clock_when_omitted(self):
        repository = InMemoryMarketStateRepository()
        for state in _series(2):
            await repository.ingest(state, raw_payload="{}")
        before = datetime.now(timezone.utc)
        report = await profile_market_state_range(repository, _config())
        after = datetime.now(timezone.utc)
        generated_at = datetime.fromisoformat(report.run_metadata.generated_at)
        assert before <= generated_at <= after


class TestSerialization:
    def test_stable_key_order(self):
        report = profile_market_state_series(_series(3), _config(), FIXED_GENERATED_AT)
        d = profiling_report_to_dict(report)
        assert list(d.keys()) == [
            "run_metadata", "data_quality", "fact_metrics", "setup_metrics",
            "setup_co_detection_matrix", "hierarchy_summary",
        ]

    def test_undefined_rates_serialize_as_null(self):
        states = [_state(event_id="e0", atr=None)]  # displacement insufficient
        report = profile_market_state_series(states, _config(), FIXED_GENERATED_AT)
        d = profiling_report_to_dict(report)
        assert d["fact_metrics"]["displacement"]["firing_rate"] is None

    def test_json_dumps_safe(self):
        import json
        report = profile_market_state_series(_series(3), _config(), FIXED_GENERATED_AT)
        json.dumps(profiling_report_to_dict(report))

    def test_no_nan_or_infinity_leaks_through(self):
        from atlas.profiling.serialization import _json_safe_float
        assert _json_safe_float(float("nan")) is None
        assert _json_safe_float(float("inf")) is None
        assert _json_safe_float(float("-inf")) is None
        assert _json_safe_float(1.5) == 1.5

    def test_schema_version_is_1_0(self):
        report = profile_market_state_series(_series(3), _config(), FIXED_GENERATED_AT)
        d = profiling_report_to_dict(report)
        assert d["run_metadata"]["schema_version"] == "1.0"

    def test_no_profitability_or_signal_terminology_in_serialized_keys(self):
        report = profile_market_state_series(_series(3), _config(), FIXED_GENERATED_AT)
        d = profiling_report_to_dict(report)
        text = str(list(_flatten_keys(d)))
        for banned in ("profit", "pnl", "signal", "confidence", "entry", "exit", "score"):
            assert banned not in text.lower()


def _flatten_keys(value):
    if isinstance(value, dict):
        for key, sub in value.items():
            yield key
            yield from _flatten_keys(sub)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_keys(item)

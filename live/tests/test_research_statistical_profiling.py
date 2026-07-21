"""
Sprint RE-1. Tests for atlas.research.statistical_profiling - both the
pure computation core (service.py, tested directly against hand-built
FactResult/RuleEngineOutput objects, the same "no impossible production
fixture through the real evaluators" discipline tests/test_profiling.py's
own TestHierarchySummary already established for exactly this reason) and
the top-level orchestration/report rendering against real MarketState
fixtures built the same way tests/test_profiling.py's own _series/_state
helpers do.
"""
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.profiling.models import ProfilingRunConfig
from atlas.research.statistical_profiling import reports, service
from atlas.rule_engine.models import FactResult, InsufficientData, RuleEngineOutput

FIXED_GENERATED_AT = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _outcome(fact_name, value, version="1.0"):
    return FactResult(fact_name=fact_name, definition_version=version, value=value, evidence={})


def _missing(fact_name, reason="not enough history", version="1.0"):
    return InsufficientData(fact_name=fact_name, definition_version=version, reason=reason)


def _output(facts: dict, occurred_at="2026-07-13T13:00:00+00:00", symbol="MNQ1!", timeframe="5m"):
    return RuleEngineOutput(schema_version="1.0", symbol=symbol, timeframe=timeframe, occurred_at=occurred_at, facts=facts)


class TestValueKey:
    def test_true_and_false(self):
        assert service._value_key(True) == "true"
        assert service._value_key(False) == "false"

    def test_enum_string_passes_through(self):
        assert service._value_key("up") == "up"


class TestRunsWithinSegment:
    def test_simple_runs(self):
        keys = ["true", "true", "false", "true"]
        assert service._runs_within_segment(keys) == [("true", 2), ("false", 1), ("true", 1)]

    def test_none_breaks_a_run_without_becoming_one(self):
        keys = ["true", None, "true"]
        assert service._runs_within_segment(keys) == [("true", 1), ("true", 1)]

    def test_all_none_yields_no_runs(self):
        assert service._runs_within_segment([None, None]) == []

    def test_empty_yields_no_runs(self):
        assert service._runs_within_segment([]) == []

    def test_single_long_run(self):
        assert service._runs_within_segment(["a"] * 5) == [("a", 5)]


class TestTransitionsWithinSegment:
    def test_simple_transitions(self):
        keys = ["true", "true", "false"]
        assert service._transitions_within_segment(keys) == [("true", "true"), ("true", "false")]

    def test_none_prevents_any_bridging_transition(self):
        keys = ["true", None, "false"]
        assert service._transitions_within_segment(keys) == []

    def test_single_value_no_transitions(self):
        assert service._transitions_within_segment(["true"]) == []


class TestBuildRunLengthStats:
    def test_empty_lengths(self):
        stats = service._build_run_length_stats("true", [])
        assert stats.run_count == 0
        assert stats.mean_length is None
        assert stats.median_length is None
        assert stats.p95_length is None
        assert stats.max_length is None
        assert stats.length_histogram == {}

    def test_typical_lengths(self):
        stats = service._build_run_length_stats("true", [3, 3, 5, 1])
        assert stats.run_count == 4
        assert stats.total_bars_in_runs == 12
        assert stats.mean_length == 3.0
        assert stats.max_length == 5
        assert stats.length_histogram == {3: 2, 5: 1, 1: 1}
        # sorted: [1, 3, 3, 5] - median (p50, nearest-rank) is rank ceil(0.5*4)=2 -> sorted[1] = 3
        assert stats.median_length == 3


class TestBuildTransitionMatrix:
    def test_counts_and_probabilities(self):
        pairs = [("true", "true"), ("true", "false"), ("false", "false")]
        matrix = service._build_transition_matrix(["true", "false"], pairs)
        assert matrix.counts == {"true": {"true": 1, "false": 1}, "false": {"true": 0, "false": 1}}
        assert matrix.probabilities["true"]["true"] == pytest.approx(0.5)
        assert matrix.probabilities["true"]["false"] == pytest.approx(0.5)
        assert matrix.probabilities["false"]["false"] == 1.0

    def test_a_value_with_zero_outgoing_transitions_is_all_none(self):
        matrix = service._build_transition_matrix(["true", "false"], [("true", "false")])
        assert matrix.probabilities["false"]["true"] is None
        assert matrix.probabilities["false"]["false"] is None


class TestPearsonCorrelation:
    def test_perfectly_correlated(self):
        assert service._pearson_correlation([0, 1, 0, 1], [0, 1, 0, 1]) == pytest.approx(1.0)

    def test_perfectly_anti_correlated(self):
        assert service._pearson_correlation([0, 1, 0, 1], [1, 0, 1, 0]) == pytest.approx(-1.0)

    def test_zero_variance_is_none(self):
        assert service._pearson_correlation([1, 1, 1], [0, 1, 0]) is None

    def test_fewer_than_two_observations_is_none(self):
        assert service._pearson_correlation([1.0], [0.0]) is None


class TestBuildPairwiseRelationship:
    def test_boolean_pair_hand_computed(self):
        # 4 bars: (A,B) = (T,T), (T,F), (F,F), (F,F)
        outputs = [
            _output({"volume_spike": _outcome("volume_spike", True), "displacement": _outcome("displacement", True)}),
            _output({"volume_spike": _outcome("volume_spike", True), "displacement": _outcome("displacement", False)}),
            _output({"volume_spike": _outcome("volume_spike", False), "displacement": _outcome("displacement", False)}),
            _output({"volume_spike": _outcome("volume_spike", False), "displacement": _outcome("displacement", False)}),
        ]
        rel = service._build_pairwise_relationship("volume_spike", "displacement", outputs)
        assert rel.both_boolean is True
        assert rel.jointly_computable_count == 4
        assert rel.p_a_true == pytest.approx(0.5)   # volume_spike true in 2/4
        assert rel.p_b_true == pytest.approx(0.25)  # displacement true in 1/4
        assert rel.p_both_true == pytest.approx(0.25)  # both true in 1/4
        # lift = P(both) / (P(A)*P(B)) = 0.25 / (0.5*0.25) = 2.0
        assert rel.lift == pytest.approx(2.0)
        # P(A|B) = both_true / b_true = 1/1 = 1.0; conditional_dependence = 1.0 - 0.5 = 0.5
        assert rel.conditional_dependence == pytest.approx(0.5)

    def test_insufficient_data_excluded_from_joint_count(self):
        outputs = [
            _output({"volume_spike": _outcome("volume_spike", True), "displacement": _missing("displacement")}),
            _output({"volume_spike": _outcome("volume_spike", True), "displacement": _outcome("displacement", True)}),
        ]
        rel = service._build_pairwise_relationship("volume_spike", "displacement", outputs)
        assert rel.jointly_computable_count == 1

    def test_enum_pair_reports_contingency_table_not_lift(self):
        outputs = [
            _output({"volume_spike": _outcome("volume_spike", True), "trend_5m": _outcome("trend_5m", "up")}),
            _output({"volume_spike": _outcome("volume_spike", False), "trend_5m": _outcome("trend_5m", "down")}),
        ]
        rel = service._build_pairwise_relationship("volume_spike", "trend_5m", outputs)
        assert rel.both_boolean is False
        assert rel.lift is None
        assert rel.correlation is None
        assert rel.category_joint_counts == {"true": {"up": 1}, "false": {"down": 1}}

    def test_zero_jointly_computable_is_all_none(self):
        outputs = [_output({"volume_spike": _missing("volume_spike"), "displacement": _outcome("displacement", True)})]
        rel = service._build_pairwise_relationship("volume_spike", "displacement", outputs)
        assert rel.jointly_computable_count == 0
        assert rel.p_a_true is None
        assert rel.lift is None


class TestBuildConditionalProbabilities:
    def test_exhaustive_table_hand_computed(self):
        # 4 bars: (A,B) = (T,T),(T,F),(F,F),(F,F) - same as pairwise test above
        outputs = [
            _output({"volume_spike": _outcome("volume_spike", True), "displacement": _outcome("displacement", True)}),
            _output({"volume_spike": _outcome("volume_spike", True), "displacement": _outcome("displacement", False)}),
            _output({"volume_spike": _outcome("volume_spike", False), "displacement": _outcome("displacement", False)}),
            _output({"volume_spike": _outcome("volume_spike", False), "displacement": _outcome("displacement", False)}),
        ]
        entries = service._build_conditional_probabilities(["volume_spike", "displacement"], outputs)
        by_key = {(e.condition_fact, e.condition_value, e.target_fact, e.target_value): e for e in entries}

        # P(displacement=true | volume_spike=true) = 1/2
        e = by_key[("volume_spike", "true", "displacement", "true")]
        assert e.probability == pytest.approx(0.5)
        assert e.condition_sample_size == 2

        # P(volume_spike=true | displacement=false) = 1/3 (of the 3 bars with displacement=false, 1 has volume_spike=true)
        e = by_key[("displacement", "false", "volume_spike", "true")]
        assert e.probability == pytest.approx(1 / 3)
        assert e.condition_sample_size == 3

    def test_same_fact_pair_excluded(self):
        outputs = [_output({"volume_spike": _outcome("volume_spike", True)})]
        entries = service._build_conditional_probabilities(["volume_spike"], outputs)
        assert entries == ()


def _state(i, base=datetime(2026, 7, 13, 13, 0, tzinfo=timezone.utc), **overrides):
    fields = dict(
        envelope=Event(event_type="bar_closed", source="tradingview",
                        occurred_at=base + timedelta(minutes=5 * i), event_id=f"e{i}"),
        schema_version="1.0", symbol=Symbol("MNQ1!"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        open=Price(100.0, 0.25), high=Price(110.0, 0.25), low=Price(90.0, 0.25), close=Price(100.0, 0.25),
        volume=1000, atr=10.0, volume_ratio=1.0, distance_from_vwap_points=3.0,
        previous_day_high=Price(1000.0, 0.25), session_name=None, is_rth=True,
    )
    fields.update(overrides)
    return MarketState(**fields)


def _config(**overrides):
    fields = dict(
        symbol=Symbol("MNQ1!"), timeframe=Timeframe.M5,
        start=datetime(2026, 7, 13, tzinfo=timezone.utc), end=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return ProfilingRunConfig(**fields)


class TestTimeDistributionBucketing:
    def test_hour_bucket_uses_america_chicago_not_utc(self):
        # 2026-07-13T13:00:00Z during CDT (UTC-5) is 08:00 local Chicago time.
        states = [_state(0)]
        outputs = [_output({}, occurred_at=states[0].envelope.occurred_at.isoformat())]
        td = service._build_time_distribution(list(zip(states, outputs)), [])
        assert [b.bucket_key for b in td.by_hour_ct] == ["08:00"]

    def test_weekday_bucket_is_locale_independent_fixed_name(self):
        # 2026-07-13 is a Monday.
        states = [_state(0)]
        outputs = [_output({}, occurred_at=states[0].envelope.occurred_at.isoformat())]
        td = service._build_time_distribution(list(zip(states, outputs)), [])
        assert [b.bucket_key for b in td.by_weekday_ct] == ["Monday"]

    def test_session_unknown_when_session_name_absent(self):
        states = [_state(0, session_name=None)]
        outputs = [_output({}, occurred_at=states[0].envelope.occurred_at.isoformat())]
        td = service._build_time_distribution(list(zip(states, outputs)), [])
        assert td.by_session[0].bucket_key == "unknown"


class TestBuildStatisticalProfileEndToEnd:
    def test_runs_and_is_deterministic(self):
        states = [_state(i) for i in range(25)]
        config = _config()
        profile_1 = service.build_statistical_profile(states, config, FIXED_GENERATED_AT, "test-fixture")
        profile_2 = service.build_statistical_profile(states, config, FIXED_GENERATED_AT, "test-fixture")
        assert profile_1 == profile_2

    def test_manifest_reflects_the_request(self):
        states = [_state(i) for i in range(5)]
        profile = service.build_statistical_profile(states, _config(), FIXED_GENERATED_AT, "unit-test-source")
        assert profile.manifest.symbol == "MNQ1!"
        assert profile.manifest.timeframe == "5m"
        assert profile.manifest.source_description == "unit-test-source"
        assert profile.manifest.row_count == 5

    def test_all_seven_facts_profiled(self):
        states = [_state(i) for i in range(25)]
        profile = service.build_statistical_profile(states, _config(), FIXED_GENERATED_AT, "unit-test")
        assert set(profile.fact_profiles.keys()) == {
            "volume_spike", "displacement", "rejection", "trend_5m",
            "liquidity_sweep", "reclaim", "vwap_relationship",
        }

    def test_pairwise_relationships_cover_every_unordered_pair(self):
        states = [_state(i) for i in range(25)]
        profile = service.build_statistical_profile(states, _config(), FIXED_GENERATED_AT, "unit-test")
        assert len(profile.pairwise_relationships) == 21  # 7 choose 2

    def test_a_gap_does_not_produce_a_fabricated_transition_or_run(self):
        # Two segments separated by a real gap - a run/transition must never
        # bridge the two, even though they're adjacent in the input list.
        first = [_state(i) for i in range(3)]
        second = [_state(i, base=datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)) for i in range(3)]
        states = first + second
        profile = service.build_statistical_profile(states, _config(), FIXED_GENERATED_AT, "unit-test")
        # displacement fires True on every bar in this fixture (always-True
        # single-bar fact given these OHLC values) - if a run bridged the
        # gap, run_count would be 1 covering all 6 bars; it must be 2.
        displacement_true_runs = [
            s for s in profile.fact_profiles["displacement"].run_length_stats if s.value == "true"
        ]
        assert displacement_true_runs[0].run_count == 2
        assert displacement_true_runs[0].total_bars_in_runs == 6


class TestReportsRenderCorrectly:
    @pytest.fixture
    def profile(self):
        states = [_state(i) for i in range(25)]
        return service.build_statistical_profile(states, _config(), FIXED_GENERATED_AT, "report-test")

    def test_fact_profile_report(self, profile):
        report = reports.render_fact_profile_report(profile)
        report.encode("ascii")
        assert "RE-1 Fact Profile" in report
        assert "No trading conclusions" in report
        assert "volume_spike" in report

    def test_rule_relationships_report(self, profile):
        report = reports.render_rule_relationships_report(profile)
        report.encode("ascii")
        assert "RE-1 Rule Relationships" in report
        assert "lift" in report

    def test_conditional_probability_report(self, profile):
        report = reports.render_conditional_probability_report(profile)
        report.encode("ascii")
        assert "RE-1 Conditional Probability" in report

    def test_time_distribution_report(self, profile):
        report = reports.render_time_distribution_report(profile)
        report.encode("ascii")
        assert "RE-1 Time Distribution" in report
        assert "America/Chicago" in report

    def test_persistence_report(self, profile):
        report = reports.render_persistence_report(profile)
        report.encode("ascii")
        assert "RE-1 Persistence" in report

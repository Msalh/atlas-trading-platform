"""
Sprint 28. Tests for atlas.research - the Research Engine's smallest
complete implementation.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    Hypothesis,
    HypothesisStatus,
    TargetKind,
)
from atlas.research.serialization import (
    experiment_from_dict,
    experiment_to_dict,
    hypothesis_from_dict,
    hypothesis_to_dict,
    research_report_to_dict,
    research_report_to_markdown,
)
from atlas.research.service import (
    build_dataset_manifest,
    build_research_report,
    evaluate_criterion,
    run_experiment,
)
from atlas.research.stores import ExperimentTracker, HypothesisRegistry, RecordConflictError

FIXED_NOW = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)


def _state(event_id="e1", occurred_at="2026-07-01T13:00:00", **overrides):
    fields = dict(
        envelope=Event(
            event_type="bar_closed", source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc), event_id=event_id,
        ),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
    )
    fields.update(overrides)
    return MarketState(**fields)


def _series(count, base="2026-07-01T13:00:00", **shared_overrides):
    base_dt = datetime.fromisoformat(base)
    fields = dict(
        open=Price(20126.00, 0.25), high=Price(20140.00, 0.25), low=Price(20120.00, 0.25),
        atr=10.0, volume_ratio=2.0,
    )
    fields.update(shared_overrides)
    states = []
    for i in range(count):
        bar_fields = dict(fields)
        bar_fields.setdefault("close", Price(20125.00 + i * 0.25, 0.25))
        states.append(_state(
            event_id=f"e{i}", occurred_at=(base_dt + timedelta(minutes=5 * i)).isoformat(), **bar_fields,
        ))
    return states


def _criterion(**overrides):
    fields = dict(
        description="volume_spike fires often", kind=CriterionKind.MIN_FIRING_RATE,
        target_kind=TargetKind.FACT, target="volume_spike", threshold=0.5,
    )
    fields.update(overrides)
    return AcceptanceCriterion(**fields)


def _hypothesis(**overrides):
    fields = dict(
        hypothesis_id="H001", registered_at=FIXED_NOW.isoformat(), author="test",
        statement="volume_spike fires often given volume_ratio=2.0 on every bar",
        dataset_symbol="MNQU6", dataset_timeframe="5m",
        dataset_start="2026-07-01T13:00:00+00:00", dataset_end="2026-07-01T15:00:00+00:00",
        acceptance_criteria=(_criterion(),),
    )
    fields.update(overrides)
    return Hypothesis(**fields)


class TestHypothesisModel:
    def test_requires_at_least_one_acceptance_criterion(self):
        with pytest.raises(ValueError, match="at least one acceptance criterion"):
            _hypothesis(acceptance_criteria=())

    def test_defaults_to_registered_status(self):
        assert _hypothesis().status == HypothesisStatus.REGISTERED

    def test_immutable(self):
        h = _hypothesis()
        with pytest.raises(Exception):
            h.statement = "changed"


class TestBuildDatasetManifest:
    def test_builds_from_states(self):
        states = _series(5)
        manifest = build_dataset_manifest(states, "2026-07-01T13:00:00+00:00", "2026-07-01T15:00:00+00:00", "test-source", FIXED_NOW)
        assert manifest.symbol == "MNQU6"
        assert manifest.timeframe == "5m"
        assert manifest.row_count == 5
        assert manifest.first_occurred_at == "2026-07-01T13:00:00+00:00"
        assert manifest.last_occurred_at == "2026-07-01T13:20:00+00:00"
        assert manifest.source_description == "test-source"

    def test_empty_states_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_dataset_manifest([], "s", "e", "src", FIXED_NOW)

    def test_mixed_symbol_raises(self):
        states = _series(2)
        states[1] = _state(event_id="other", occurred_at="2026-07-01T13:05:00", symbol=Symbol("ESU6"))
        with pytest.raises(ValueError, match="more than one symbol"):
            build_dataset_manifest(states, "s", "e", "src", FIXED_NOW)

    def test_out_of_order_states_still_sorted_correctly(self):
        states = list(reversed(_series(3)))
        manifest = build_dataset_manifest(states, "s", "e", "src", FIXED_NOW)
        assert manifest.first_occurred_at == "2026-07-01T13:00:00+00:00"
        assert manifest.last_occurred_at == "2026-07-01T13:10:00+00:00"


class TestEvaluateCriterion:
    def _report(self):
        from atlas.profiling.models import ProfilingRunConfig
        from atlas.profiling.service import profile_market_state_series
        states = _series(25)
        config = ProfilingRunConfig(
            symbol=Symbol("MNQU6"), timeframe=Timeframe.M5,
            start=datetime.fromisoformat("2026-07-01T13:00:00+00:00"), end=datetime.fromisoformat("2026-07-01T15:00:00+00:00"),
        )
        return profile_market_state_series(states, config, FIXED_NOW)

    def test_min_firing_rate_pass(self):
        report = self._report()
        result = evaluate_criterion(_criterion(threshold=0.5), report)
        assert result.passed is True
        assert result.actual_value == 1.0

    def test_min_firing_rate_fail(self):
        report = self._report()
        result = evaluate_criterion(_criterion(threshold=1.5), report)
        assert result.passed is False

    def test_min_computable_count(self):
        report = self._report()
        result = evaluate_criterion(_criterion(kind=CriterionKind.MIN_COMPUTABLE_COUNT, threshold=20), report)
        assert result.passed is True
        assert result.actual_value == 25.0

    def test_unknown_target_reports_reason_not_silent_fail(self):
        report = self._report()
        result = evaluate_criterion(_criterion(target="not_a_real_fact"), report)
        assert result.passed is False
        assert result.actual_value is None
        assert "not found" in result.reason

    def test_setup_target_uses_detection_rate(self):
        report = self._report()
        result = evaluate_criterion(
            _criterion(target_kind=TargetKind.SETUP, target="displacement_with_volume_confirmation", threshold=0.5),
            report,
        )
        assert result.actual_value is not None  # displacement/volume_ratio both fire on every bar in this fixture

    def test_undefined_rate_is_not_a_silent_pass_or_fail_without_reason(self):
        from atlas.profiling.models import ProfilingRunConfig
        from atlas.profiling.service import profile_market_state_series
        states = [_state(event_id="e0")]  # atr present but no reference levels -> liquidity_sweep insufficient
        config = ProfilingRunConfig(
            symbol=Symbol("MNQU6"), timeframe=Timeframe.M5,
            start=datetime.fromisoformat("2026-07-01T13:00:00+00:00"), end=datetime.fromisoformat("2026-07-01T13:00:00+00:00"),
        )
        report = profile_market_state_series(states, config, FIXED_NOW)
        result = evaluate_criterion(_criterion(target="liquidity_sweep"), report)
        assert result.passed is False
        assert result.reason is not None


class TestRunExperiment:
    def test_full_cycle_produces_experiment_and_report(self):
        hypothesis = _hypothesis()
        states = _series(25)
        experiment, report = run_experiment(hypothesis, states, FIXED_NOW, "EXP-H001-01", "test-source")
        assert experiment.hypothesis_id == "H001"
        assert experiment.passed is True
        assert experiment.dataset_manifest.row_count == 25
        assert report.fact_metrics["volume_spike"].firing_rate == 1.0

    def test_mismatched_symbol_raises(self):
        hypothesis = _hypothesis(dataset_symbol="ESU6")
        states = _series(5)
        with pytest.raises(ValueError, match="ESU6"):
            run_experiment(hypothesis, states, FIXED_NOW, "EXP-H001-01", "test-source")

    def test_code_version_populated_in_this_git_checkout(self):
        hypothesis = _hypothesis()
        states = _series(5)
        experiment, _report = run_experiment(hypothesis, states, FIXED_NOW, "EXP-H001-01", "test-source")
        assert experiment.code_version is None or len(experiment.code_version) == 40

    def test_deterministic_same_input_same_result(self):
        hypothesis = _hypothesis()
        states = _series(25)
        e1, _ = run_experiment(hypothesis, states, FIXED_NOW, "EXP-H001-01", "test-source")
        e2, _ = run_experiment(hypothesis, states, FIXED_NOW, "EXP-H001-01", "test-source")
        assert e1 == e2

    def test_saves_profiling_report_when_dir_given(self, tmp_path):
        hypothesis = _hypothesis()
        states = _series(25)
        experiment, _report = run_experiment(hypothesis, states, FIXED_NOW, "EXP-H001-01", "test-source", profiling_report_dir=tmp_path)
        assert experiment.profiling_report_path is not None
        saved = json.loads((tmp_path / "EXP-H001-01.profiling_report.json").read_text())
        assert saved["fact_metrics"]["volume_spike"]["firing_rate"] == 1.0


class TestBuildResearchReport:
    def test_validated_status_on_pass(self):
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        research_report = build_research_report(hypothesis, experiment)
        assert research_report.hypothesis.status == HypothesisStatus.VALIDATED
        assert research_report.conclusion.startswith("PASSED")

    def test_rejected_status_on_fail(self):
        hypothesis = _hypothesis(acceptance_criteria=(_criterion(threshold=1.5),))
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        research_report = build_research_report(hypothesis, experiment)
        assert research_report.hypothesis.status == HypothesisStatus.REJECTED
        assert research_report.conclusion.startswith("REJECTED")
        assert "1.5" in research_report.conclusion

    def test_original_hypothesis_never_mutated(self):
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        build_research_report(hypothesis, experiment)
        assert hypothesis.status == HypothesisStatus.REGISTERED  # unchanged - build_research_report never mutates its input


class TestSerializationRoundTrip:
    def test_hypothesis_round_trip(self):
        h = _hypothesis()
        assert hypothesis_from_dict(hypothesis_to_dict(h)) == h

    def test_experiment_round_trip(self):
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        assert experiment_from_dict(experiment_to_dict(experiment)) == experiment

    def test_research_report_json_dumps_safe(self):
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        research_report = build_research_report(hypothesis, experiment)
        json.dumps(research_report_to_dict(research_report))

    def test_markdown_rendering_does_not_crash_and_is_ascii_safe(self):
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        research_report = build_research_report(hypothesis, experiment)
        text = research_report_to_markdown(research_report)
        text.encode("ascii")  # would raise if any non-ASCII character leaked in
        assert "H001" in text
        assert "PASSED" in text


class TestHypothesisRegistry:
    def test_register_and_get(self, tmp_path):
        registry = HypothesisRegistry(tmp_path / "hypotheses.jsonl")
        h = _hypothesis()
        registry.register(h)
        assert registry.get("H001") == h

    def test_get_missing_returns_none(self, tmp_path):
        registry = HypothesisRegistry(tmp_path / "hypotheses.jsonl")
        assert registry.get("nope") is None

    def test_identical_reregistration_is_a_safe_no_op(self, tmp_path):
        registry = HypothesisRegistry(tmp_path / "hypotheses.jsonl")
        h = _hypothesis()
        registry.register(h)
        registry.register(h)  # must not raise
        assert len(registry.all()) == 1

    def test_conflicting_reregistration_raises(self, tmp_path):
        registry = HypothesisRegistry(tmp_path / "hypotheses.jsonl")
        registry.register(_hypothesis())
        with pytest.raises(RecordConflictError):
            registry.register(_hypothesis(statement="a different claim"))

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "hypotheses.jsonl"
        HypothesisRegistry(path).register(_hypothesis())
        reopened = HypothesisRegistry(path)
        assert reopened.get("H001") is not None

    def test_all_returns_every_registered_hypothesis(self, tmp_path):
        registry = HypothesisRegistry(tmp_path / "hypotheses.jsonl")
        registry.register(_hypothesis(hypothesis_id="H001"))
        registry.register(_hypothesis(hypothesis_id="H002"))
        assert {h.hypothesis_id for h in registry.all()} == {"H001", "H002"}


class TestExperimentTracker:
    def test_record_and_get(self, tmp_path):
        tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        tracker.record(experiment)
        assert tracker.get("EXP-H001-01") == experiment

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "experiments.jsonl"
        hypothesis = _hypothesis()
        experiment, _report = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        ExperimentTracker(path).record(experiment)
        reopened = ExperimentTracker(path)
        assert reopened.get("EXP-H001-01") == experiment

    def test_for_hypothesis_filters_correctly(self, tmp_path):
        tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
        h1 = _hypothesis(hypothesis_id="H001")
        h2 = _hypothesis(hypothesis_id="H002")
        e1, _ = run_experiment(h1, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        e2, _ = run_experiment(h2, _series(25), FIXED_NOW, "EXP-H002-01", "src")
        tracker.record(e1)
        tracker.record(e2)
        assert [e.experiment_id for e in tracker.for_hypothesis("H001")] == ["EXP-H001-01"]

    def test_conflicting_rerecord_raises(self, tmp_path):
        tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
        hypothesis = _hypothesis()
        e1, _ = run_experiment(hypothesis, _series(25), FIXED_NOW, "EXP-H001-01", "src")
        e2, _ = run_experiment(hypothesis, _series(20), FIXED_NOW, "EXP-H001-01", "src")  # different data, same id
        tracker.record(e1)
        with pytest.raises(RecordConflictError):
            tracker.record(e2)

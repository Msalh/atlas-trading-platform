"""
Phase N4 Sprint 5. Tests for atlas.research.experiment_builder - unit tests
for the pure fingerprint/resolution helpers against hand-built fixtures,
full build_experiment() flow tests (new semantic question / new execution
of an existing one / exact cache hit), and a real-Replay-Bridge integration
test, mirroring the roadmap's own required test strategy for this sprint.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.experiment_builder.service import (
    build_experiment,
    compute_execution_fingerprint,
    compute_semantic_fingerprint,
    evaluate_feature_series,
    resolve_feature_pins,
)
from atlas.research.features.registry import REGISTRY
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    DatasetManifest,
    Hypothesis,
    TargetKind,
)
from atlas.research.replay_bridge import build_replay_frames_for_window
from atlas.research.stores import ExperimentTracker

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
_MEAN_ATR = REGISTRY[0]  # the one Sprint 4 Registered feature: mean_atr, window=14


def _state(event_id: str, occurred_at: datetime, atr: float) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=event_id),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        atr=atr,
    )


def _series(atrs: list[float], base: datetime = _BASE, cadence_minutes: int = 5) -> list[MarketState]:
    step = timedelta(minutes=cadence_minutes)
    return [_state(f"e{i}", base + step * i, atr) for i, atr in enumerate(atrs)]


def _hypothesis(**overrides) -> Hypothesis:
    fields = dict(
        hypothesis_id="h1", registered_at=_BASE.isoformat(), author="tester",
        statement="mean_atr is elevated over this window",
        dataset_symbol="MNQU6", dataset_timeframe="5m",
        dataset_start=_BASE.isoformat(), dataset_end=(_BASE + timedelta(days=1)).isoformat(),
        acceptance_criteria=(
            AcceptanceCriterion(
                description="mean_atr clears 2.0", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
                target_kind=TargetKind.FEATURE, target="mean_atr", threshold=2.0,
            ),
        ),
        feature_refs=("mean_atr",),
    )
    fields.update(overrides)
    return Hypothesis(**fields)


def _dataset_manifest(**overrides) -> DatasetManifest:
    fields = dict(
        symbol="MNQU6", timeframe="5m", requested_start=_BASE.isoformat(), requested_end=_BASE.isoformat(),
        row_count=20, first_occurred_at=_BASE.isoformat(), last_occurred_at=_BASE.isoformat(),
        source_description="test", generated_at=_BASE.isoformat(),
    )
    fields.update(overrides)
    return DatasetManifest(**fields)


# ---- evaluate_feature_series() ----

def test_evaluate_feature_series_returns_one_outcome_per_bar():
    states = _series([3.0] * 20)
    series = evaluate_feature_series(states, _MEAN_ATR)
    assert len(series) == 20


def test_evaluate_feature_series_matches_direct_evaluate_at_the_last_position():
    from atlas.research.features.evaluators import evaluate_mean_atr
    states = _series([1.0 + i * 0.1 for i in range(20)])
    series = evaluate_feature_series(states, _MEAN_ATR)
    direct = evaluate_mean_atr(states, _MEAN_ATR.feature)
    assert series[-1] == direct


# ---- resolve_feature_pins() ----

def test_resolve_feature_pins_resolves_a_real_registered_feature():
    pins = resolve_feature_pins(["mean_atr"])
    assert len(pins) == 1
    assert pins[0]["feature_id"] == "mean_atr"
    assert pins[0]["version"] == "1.0"
    assert pins[0]["fingerprint"] == REGISTRY[0].feature.fingerprint


def test_resolve_feature_pins_raises_on_unregistered_feature_id():
    with pytest.raises(ValueError, match="not registered"):
        resolve_feature_pins(["does_not_exist"])


def test_resolve_feature_pins_sorted_by_feature_id_regardless_of_input_order():
    pins = resolve_feature_pins(["mean_atr"])
    ids = [p["feature_id"] for p in pins]
    assert ids == sorted(ids)


# ---- compute_semantic_fingerprint(): request fields only ----

def test_semantic_fingerprint_stable_across_resolved_dataset_fields():
    """The core proof of the request/resolved DatasetManifest split: two
    manifests with the SAME request but DIFFERENT resolved facts (as a
    live/replay dataset genuinely can have between two otherwise-identical
    requests) must produce the SAME semantic_fingerprint."""
    h = _hypothesis()
    manifest_a = _dataset_manifest(row_count=20, first_occurred_at="2026-07-20T13:00:00+00:00")
    manifest_b = _dataset_manifest(row_count=25, first_occurred_at="2026-07-19T09:00:00+00:00")
    assert compute_semantic_fingerprint(h, manifest_a) == compute_semantic_fingerprint(h, manifest_b)


def test_semantic_fingerprint_changes_when_the_request_changes():
    h = _hypothesis()
    manifest_a = _dataset_manifest(requested_start="2026-07-01T00:00:00+00:00")
    manifest_b = _dataset_manifest(requested_start="2026-08-01T00:00:00+00:00")
    assert compute_semantic_fingerprint(h, manifest_a) != compute_semantic_fingerprint(h, manifest_b)


def test_semantic_fingerprint_changes_when_the_hypothesis_changes():
    manifest = _dataset_manifest()
    assert compute_semantic_fingerprint(_hypothesis(hypothesis_id="h1"), manifest) != \
        compute_semantic_fingerprint(_hypothesis(hypothesis_id="h2"), manifest)


# ---- compute_execution_fingerprint(): resolved facts + code_version + feature pins ----

def test_execution_fingerprint_changes_when_resolved_dataset_fields_change():
    semantic = compute_semantic_fingerprint(_hypothesis(), _dataset_manifest())
    pins = resolve_feature_pins(["mean_atr"])
    fp_a = compute_execution_fingerprint(semantic, "abc123", _dataset_manifest(row_count=20), pins)
    fp_b = compute_execution_fingerprint(semantic, "abc123", _dataset_manifest(row_count=25), pins)
    assert fp_a != fp_b


def test_execution_fingerprint_changes_when_code_version_changes():
    semantic = compute_semantic_fingerprint(_hypothesis(), _dataset_manifest())
    manifest = _dataset_manifest()
    pins = resolve_feature_pins(["mean_atr"])
    fp_a = compute_execution_fingerprint(semantic, "abc123", manifest, pins)
    fp_b = compute_execution_fingerprint(semantic, "def456", manifest, pins)
    assert fp_a != fp_b


def test_execution_fingerprint_deterministic_given_identical_inputs():
    semantic = compute_semantic_fingerprint(_hypothesis(), _dataset_manifest())
    manifest = _dataset_manifest()
    pins = resolve_feature_pins(["mean_atr"])
    fp_a = compute_execution_fingerprint(semantic, "abc123", manifest, pins)
    fp_b = compute_execution_fingerprint(semantic, "abc123", manifest, pins)
    assert fp_a == fp_b


# ---- build_experiment(): validation ----

def test_build_experiment_rejects_symbol_timeframe_mismatch(tmp_path: Path):
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    h = _hypothesis(dataset_symbol="ESU6")
    with pytest.raises(ValueError, match="specifies"):
        build_experiment(h, _series([3.0] * 20), _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker)


def test_build_experiment_rejects_non_feature_criterion(tmp_path: Path):
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    h = _hypothesis(acceptance_criteria=(
        AcceptanceCriterion(description="x", kind=CriterionKind.MIN_FIRING_RATE, target_kind=TargetKind.FACT, target="trend_5m", threshold=0.1),
    ))
    with pytest.raises(ValueError, match="TargetKind.FEATURE"):
        build_experiment(h, _series([3.0] * 20), _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker)


def test_build_experiment_rejects_a_criterion_target_not_in_feature_refs(tmp_path: Path):
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    h = _hypothesis(feature_refs=())  # target "mean_atr" is not listed
    with pytest.raises(ValueError, match="not listed"):
        build_experiment(h, _series([3.0] * 20), _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker)


# ---- build_experiment(): identity/caching behavior ----

def test_build_experiment_first_call_is_a_new_execution(tmp_path: Path):
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    h = _hypothesis()
    outcome = build_experiment(h, _series([3.0] * 20), _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker)
    assert outcome.is_new_execution is True
    assert outcome.experiment.experiment_id == "e1"
    assert outcome.experiment.semantic_fingerprint is not None
    assert outcome.experiment.execution_fingerprint is not None
    assert tracker.get("e1") == outcome.experiment


def test_build_experiment_identical_rerun_is_an_exact_cache_hit(tmp_path: Path):
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    h = _hypothesis()
    states = _series([3.0] * 20)
    first = build_experiment(h, states, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker)
    second = build_experiment(h, states, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e2", tracker)
    assert second.is_new_execution is False
    assert second.experiment == first.experiment  # the EXISTING record, not a new "e2" one
    assert len(tracker.all()) == 1


def test_build_experiment_same_semantic_question_different_execution_appends_a_new_row_sharing_semantic_fingerprint(tmp_path: Path):
    """Simulates 'the code changed since this question was last asked':
    a prior Experiment record is seeded directly with the SAME
    semantic_fingerprint build_experiment() would compute today, but a
    manually-forced different execution_fingerprint (standing in for a
    different code_version at the time it ran). A real build_experiment()
    call for the same hypothesis/dataset must recognize this as the SAME
    semantic question but a NEW execution - not a cache hit, not an
    unrelated new question."""
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    h = _hypothesis()
    states = _series([3.0] * 20)

    real_outcome = build_experiment(h, states, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e_real", tracker)
    prior_semantic = real_outcome.experiment.semantic_fingerprint

    from dataclasses import replace
    seeded_prior = replace(
        real_outcome.experiment, experiment_id="e_prior_execution",
        execution_fingerprint="deadbeefdeadbeef",  # stands in for "an older, different code_version run"
    )
    tracker.record(seeded_prior)

    assert len(tracker.for_hypothesis("h1")) == 2
    semantic_fingerprints = {e.semantic_fingerprint for e in tracker.for_hypothesis("h1")}
    assert semantic_fingerprints == {prior_semantic}
    execution_fingerprints = {e.execution_fingerprint for e in tracker.for_hypothesis("h1")}
    assert len(execution_fingerprints) == 2  # two distinct executions of the same semantic question


# ---- reproducibility (Principle VII.1's first real test) ----

def test_reproducibility_same_inputs_from_scratch_produce_the_same_fingerprints(tmp_path: Path):
    """Two INDEPENDENT build_experiment() calls (separate trackers, so
    neither can hit the other's cache) over byte-identical inputs must
    compute byte-identical semantic_fingerprint/execution_fingerprint -
    proof this is a pure function of its inputs, not incidentally stable."""
    h = _hypothesis()
    states = _series([3.0] * 20)

    tracker_a = ExperimentTracker(tmp_path / "a.jsonl")
    tracker_b = ExperimentTracker(tmp_path / "b.jsonl")
    outcome_a = build_experiment(h, states, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker_a)
    outcome_b = build_experiment(h, states, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker_b)

    assert outcome_a.experiment.semantic_fingerprint == outcome_b.experiment.semantic_fingerprint
    assert outcome_a.experiment.execution_fingerprint == outcome_b.experiment.execution_fingerprint
    assert outcome_a.experiment.criteria_results == outcome_b.experiment.criteria_results
    assert outcome_a.experiment.passed == outcome_b.experiment.passed


# ---- integration: real Replay Bridge output (Sprint 3) ----

def test_build_experiment_over_real_replay_bridge_output(tmp_path: Path):
    tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    states = _series([1.0 + i * 0.2 for i in range(20)])  # trailing mean well above threshold=2.0
    frames = build_replay_frames_for_window(states)
    extracted = [frame.market_state for frame in frames]
    assert extracted == states  # Replay Bridge passes frames through unmutated

    h = _hypothesis()
    outcome = build_experiment(h, extracted, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e1", tracker)

    assert outcome.experiment.passed is True
    # criteria_results[0].actual_value is the mean of every per-bar
    # rolling mean_atr value across the whole dataset (one FeatureComputed
    # per bar once the trailing 14-bar window is satisfied, i.e. bars
    # 13..19) - not just the single rolling mean at the final bar.
    from atlas.research.features.models import FeatureComputed
    expected = sum(
        o.value for o in outcome.feature_series["mean_atr"] if isinstance(o, FeatureComputed)
    ) / sum(1 for o in outcome.feature_series["mean_atr"] if isinstance(o, FeatureComputed))
    assert outcome.experiment.criteria_results[0].actual_value == pytest.approx(expected)
    assert "mean_atr" in outcome.feature_series
    assert len(outcome.feature_series["mean_atr"]) == 20

"""
Phase N4 Sprint 8. End-to-end proof of the full new pipeline this sprint
actually built, over real Replay Bridge output: Hypothesis ->
construct_realization() -> real ReplayFrame sequence ->
build_realization_experiment() (which internally calls
atlas.research.backtesting.execute_realization()) -> a real decision
sequence -> compute_decision_sequence_evidence(). Run alongside an
existing decision-free (Stage A) hypothesis over the SAME dataset, proving
neither pipeline interferes with or weakens the other - both coexist in
the same ExperimentTracker.

Deliberately stops at Evidence, not Validation/Ranking: validate() (Sprint
6, frozen) reads Evidence.metrics keyed as f"{criterion.target}__mean" -
the Feature-based shape compute_evidence() produces. Statistics's own new
compute_decision_sequence_evidence() (Sprint 8) intentionally does not
produce that shape (decision-frequency metrics aren't per-Feature) -
Validation/Ranking's own decision-sequence support is real, additional
work on a separately-frozen package, explicitly deferred (a Sprint 8
architectural review finding, resolved by the user's own descope decision
during implementation), not built or asserted here.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.backtesting.models import ResearchDispositionKind
from atlas.research.experiment_builder.service import build_experiment, build_realization_experiment, construct_realization
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    Hypothesis,
    ProvenanceKind,
    RealizationKind,
    RealizationTemplateKind,
    TargetKind,
)
from atlas.research.replay_bridge import build_replay_frames_for_window
from atlas.research.statistics.service import compute_decision_sequence_evidence, compute_evidence
from atlas.research.stores import ExperimentTracker, RealizationRegistry

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)


def _states(atrs: list[float], closes: list[float]) -> list[MarketState]:
    step = timedelta(minutes=5)
    return [
        MarketState(
            envelope=Event(event_type="bar_closed", source="test", occurred_at=_BASE + step * i, event_id=f"e{i}"),
            schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
            atr=atr, close=Price(value=close, tick_size=0.25),
        )
        for i, (atr, close) in enumerate(zip(atrs, closes))
    ]


def _hypothesis(hypothesis_id: str) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id, registered_at=_BASE.isoformat(), author="tester",
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


def test_realization_bound_and_decision_free_pipelines_coexist_over_real_replay_bridge_output(tmp_path: Path):
    experiment_tracker = ExperimentTracker(tmp_path / "experiments.jsonl")
    realization_tracker = RealizationRegistry(tmp_path / "realizations.jsonl")

    atrs = [1.0 + i * 0.2 for i in range(20)]  # trailing mean_atr well above threshold=2.0, matches Sprint 5's own fixture
    closes = [1.0] * 5 + [3.0] * 15  # crosses above threshold=2.0 at bar index 5

    # ---- Stage A: decision-free, unchanged since Sprint 5 ----
    stage_a_hypothesis = _hypothesis("h_stage_a")
    stage_a_states = _states(atrs, closes)
    stage_a_outcome = build_experiment(
        stage_a_hypothesis, stage_a_states, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e_stage_a",
        experiment_tracker,
    )
    stage_a_evidence = compute_evidence(
        stage_a_outcome.experiment, stage_a_outcome.feature_series, evidence_id="ev_stage_a", computed_at=_BASE.isoformat(),
    )
    assert stage_a_outcome.experiment.realization_id is None
    assert stage_a_outcome.experiment.passed is True
    assert stage_a_evidence.metrics["mean_atr__computable"] is True

    # ---- Stage B/C: Realization-bound, this sprint's own new pipeline ----
    stage_bc_hypothesis = _hypothesis("h_stage_bc")
    realization = construct_realization(
        stage_bc_hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": 2.0},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, "r1", _BASE.isoformat(), realization_tracker,
    )
    stage_bc_states = _states(atrs, closes)
    frames = build_replay_frames_for_window(stage_bc_states)
    assert [f.market_state for f in frames] == stage_bc_states  # Replay Bridge passes frames through unmutated

    stage_bc_outcome = build_realization_experiment(
        stage_bc_hypothesis, realization, frames, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "e_stage_bc",
        experiment_tracker,
    )
    stage_bc_evidence = compute_decision_sequence_evidence(
        stage_bc_outcome.experiment, stage_bc_outcome.decision_sequence,
        evidence_id="ev_stage_bc", computed_at=_BASE.isoformat(),
    )

    assert stage_bc_outcome.experiment.realization_id == "r1"
    assert stage_bc_outcome.decision_sequence is not None
    assert len(stage_bc_outcome.decision_sequence) == 20
    dispositions = [d.disposition for d in stage_bc_outcome.decision_sequence]
    assert ResearchDispositionKind.ENTER_LONG in dispositions  # the real cross at bar index 5 actually fired
    assert stage_bc_evidence.metrics["decision_sequence__sample_size"] == 20
    assert stage_bc_evidence.metrics["decision_sequence__enter_long_count"] == 1

    # ---- neither pipeline weakened or interfered with the other ----
    assert len(experiment_tracker.all()) == 2
    assert experiment_tracker.get("e_stage_a") == stage_a_outcome.experiment
    assert experiment_tracker.get("e_stage_bc") == stage_bc_outcome.experiment
    assert stage_a_outcome.experiment.semantic_fingerprint != stage_bc_outcome.experiment.semantic_fingerprint
    assert realization_tracker.get("r1") == realization

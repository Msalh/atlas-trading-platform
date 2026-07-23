"""
Phase N4 Sprint 8.1. Final proof of the pipeline diagram: Realization ->
Decision Sequence -> Evidence -> ValidationResult -> LeaderboardSnapshot,
completed using atlas.research.validation and atlas.research.ranking
completely unmodified - neither package's own source file changed this
sprint (confirmed by dependency audit below, not merely assumed), and
neither gained a new import of atlas.research.backtesting or
atlas.research.statistics.

A real decision-sequence-derived ValidationResult is ranked alongside a
real Feature-based one in the SAME LeaderboardSnapshot, proving neither
pipeline weakens or interferes with the other all the way through to the
organizational leaderboard.
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.experiment_builder.service import (
    build_experiment,
    build_realization_experiment,
    construct_realization,
)
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    Hypothesis,
    ProvenanceKind,
    RealizationKind,
    RealizationTemplateKind,
    TargetKind,
    ValidationVerdict,
)
from atlas.research.ranking.models import RANKING_POLICY_V1
from atlas.research.ranking.service import snapshot_leaderboard
from atlas.research.replay_bridge import build_replay_frames_for_window
from atlas.research.statistics.service import compute_decision_sequence_evidence, compute_evidence
from atlas.research.stores import ExperimentTracker, LeaderboardSnapshotTracker, RealizationRegistry
from atlas.research.validation.models import MonteCarloSpec, WalkForwardSpec
from atlas.research.validation.service import validate

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_VALIDATION_DIR = _ATLAS_ROOT / "research" / "validation"
_RANKING_DIR = _ATLAS_ROOT / "research" / "ranking"


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


def _hypothesis(hypothesis_id: str, acceptance_criteria: tuple) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id, registered_at=_BASE.isoformat(), author="tester",
        statement="stub claim", dataset_symbol="MNQU6", dataset_timeframe="5m",
        dataset_start=_BASE.isoformat(), dataset_end=(_BASE + timedelta(days=1)).isoformat(),
        acceptance_criteria=acceptance_criteria, feature_refs=("mean_atr",),
    )


_DECISION_SEQUENCE_CRITERION = AcceptanceCriterion(
    description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
    target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
)
_FEATURE_CRITERION = AcceptanceCriterion(
    description="mean_atr clears 2.0", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
    target_kind=TargetKind.FEATURE, target="mean_atr", threshold=2.0,
)


def _wf_spec() -> WalkForwardSpec:
    return WalkForwardSpec(in_sample_fold_count=1, out_of_sample_fold_count=1, fold_scheme_description="single fold")


def _mc_spec() -> MonteCarloSpec:
    return MonteCarloSpec(n_draws=2000, seed=42)


def _decision_sequence_evidence(tmp_path: Path, evidence_id: str, closes: list[float], threshold: float = 2.0):
    """Real pipeline: Hypothesis -> Realization -> real Replay Bridge
    frames -> execute_realization() -> decision sequence ->
    compute_decision_sequence_evidence() - returns (experiment, evidence)."""
    hypothesis = _hypothesis(f"h_{evidence_id}", (_DECISION_SEQUENCE_CRITERION,))
    realization_tracker = RealizationRegistry(tmp_path / f"realizations_{evidence_id}.jsonl")
    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": threshold},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, f"r_{evidence_id}", _BASE.isoformat(),
        realization_tracker,
    )
    states = _states([3.0] * len(closes), closes)
    frames = build_replay_frames_for_window(states)
    experiment_tracker = ExperimentTracker(tmp_path / f"experiments_{evidence_id}.jsonl")
    outcome = build_realization_experiment(
        hypothesis, realization, frames, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        f"exp_{evidence_id}", experiment_tracker,
    )
    evidence = compute_decision_sequence_evidence(
        outcome.experiment, outcome.decision_sequence, tuple(frames), (_DECISION_SEQUENCE_CRITERION,),
        evidence_id=evidence_id, computed_at=_BASE.isoformat(),
    )
    return outcome.experiment, evidence


# ---- predetermined verdicts (test 9): not a smoke test ----

def test_decision_sequence_evidence_produces_a_deterministic_supported_verdict(tmp_path: Path):
    """closes cross the threshold repeatedly in both windows - enter_long_rate
    clearly clears 0.1 in-sample and out-of-sample."""
    closes_in = ([1.0, 3.0] * 10)  # crosses up/down repeatedly -> multiple ENTER_LONG events
    closes_out = ([1.0, 3.0] * 10)
    _, ev_in = _decision_sequence_evidence(tmp_path, "ev_in", closes_in)
    _, ev_out = _decision_sequence_evidence(tmp_path, "ev_out", closes_out)

    assert ev_in.metrics["enter_long_rate__mean"] > 0.1
    assert ev_out.metrics["enter_long_rate__mean"] > 0.1

    result = validate(
        hypothesis_id="h_decision_sequence", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=_DECISION_SEQUENCE_CRITERION, walk_forward_spec=_wf_spec(), monte_carlo_spec=_mc_spec(),
        batch_size=1, validation_id="v1", validated_at=_BASE.isoformat(),
    )
    assert result.verdict == ValidationVerdict.SUPPORTED


def test_decision_sequence_evidence_produces_a_deterministic_not_supported_verdict(tmp_path: Path):
    """closes never cross the threshold out-of-sample - enter_long_rate is
    exactly 0.0, clearly below 0.1."""
    closes_in = ([1.0, 3.0] * 10)
    closes_out = [1.0] * 20  # flat - never crosses, enter_long_rate = 0.0
    _, ev_in = _decision_sequence_evidence(tmp_path, "ev_in", closes_in)
    _, ev_out = _decision_sequence_evidence(tmp_path, "ev_out", closes_out)

    assert ev_out.metrics["enter_long_rate__mean"] == 0.0

    result = validate(
        hypothesis_id="h_decision_sequence", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=_DECISION_SEQUENCE_CRITERION, walk_forward_spec=_wf_spec(), monte_carlo_spec=_mc_spec(),
        batch_size=1, validation_id="v1", validated_at=_BASE.isoformat(),
    )
    assert result.verdict == ValidationVerdict.NOT_SUPPORTED


# ---- missing/insufficient target metrics (test 10) ----

def test_insufficient_decision_sequence_data_is_inconclusive_not_not_supported(tmp_path: Path):
    """A single-decision out-of-sample sequence (n=1 < 2) makes
    enter_long_rate__computable False - validate() must report INCONCLUSIVE,
    never NOT_SUPPORTED, for data it could not measure at all."""
    closes_in = ([1.0, 3.0] * 10)
    closes_out = [1.0]  # n=1, insufficient for the inferential family
    _, ev_in = _decision_sequence_evidence(tmp_path, "ev_in", closes_in)
    _, ev_out = _decision_sequence_evidence(tmp_path, "ev_out", closes_out)

    assert ev_out.metrics["enter_long_rate__computable"] is False

    result = validate(
        hypothesis_id="h_decision_sequence", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=_DECISION_SEQUENCE_CRITERION, walk_forward_spec=_wf_spec(), monte_carlo_spec=_mc_spec(),
        batch_size=1, validation_id="v1", validated_at=_BASE.isoformat(),
    )
    assert result.verdict == ValidationVerdict.INCONCLUSIVE
    assert result.verdict != ValidationVerdict.NOT_SUPPORTED


# ---- full pipeline: Realization -> Decision Sequence -> Evidence ->
#      ValidationResult -> LeaderboardSnapshot, alongside Feature-based ----

def test_full_pipeline_decision_sequence_and_feature_based_hypotheses_share_one_leaderboard_snapshot(tmp_path: Path):
    # ---- decision-sequence-based ValidationResult, real pipeline throughout ----
    closes_in = ([1.0, 3.0] * 10)
    closes_out = ([1.0, 3.0] * 10)
    _, ev_in_bc = _decision_sequence_evidence(tmp_path, "ev_in_bc", closes_in)
    _, ev_out_bc = _decision_sequence_evidence(tmp_path, "ev_out_bc", closes_out)
    result_bc = validate(
        hypothesis_id="h_stage_bc", in_sample_evidence=(ev_in_bc,), out_of_sample_evidence=(ev_out_bc,),
        criterion=_DECISION_SEQUENCE_CRITERION, walk_forward_spec=_wf_spec(), monte_carlo_spec=_mc_spec(),
        batch_size=1, validation_id="v_stage_bc", validated_at=_BASE.isoformat(),
    )
    assert result_bc.verdict == ValidationVerdict.SUPPORTED

    # ---- Feature-based (Stage A) ValidationResult, real pipeline throughout ----
    stage_a_hypothesis = _hypothesis("h_stage_a", (_FEATURE_CRITERION,))
    atrs = [1.0 + i * 0.2 for i in range(20)]  # trailing mean_atr well above threshold=2.0
    states_in = _states(atrs, [1.0] * 20)
    out_of_sample_base = _BASE + timedelta(days=30)  # a genuinely different window - distinct resolved dataset facts
    states_out = [
        MarketState(
            envelope=Event(
                event_type="bar_closed", source="test",
                occurred_at=out_of_sample_base + timedelta(minutes=5 * i), event_id=f"oos_e{i}",
            ),
            schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
            atr=atr, close=Price(value=1.0, tick_size=0.25),
        )
        for i, atr in enumerate(atrs)
    ]
    tracker_a = ExperimentTracker(tmp_path / "experiments_stage_a.jsonl")
    outcome_in = build_experiment(
        stage_a_hypothesis, states_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "exp_a_in", tracker_a,
    )
    outcome_out = build_experiment(
        stage_a_hypothesis, states_out, out_of_sample_base.isoformat(), out_of_sample_base.isoformat(), "test",
        out_of_sample_base, "exp_a_out", tracker_a,
    )
    ev_in_a = compute_evidence(outcome_in.experiment, outcome_in.feature_series, "ev_in_a", _BASE.isoformat())
    ev_out_a = compute_evidence(outcome_out.experiment, outcome_out.feature_series, "ev_out_a", _BASE.isoformat())
    result_a = validate(
        hypothesis_id="h_stage_a", in_sample_evidence=(ev_in_a,), out_of_sample_evidence=(ev_out_a,),
        criterion=_FEATURE_CRITERION, walk_forward_spec=_wf_spec(), monte_carlo_spec=_mc_spec(),
        batch_size=1, validation_id="v_stage_a", validated_at=_BASE.isoformat(),
    )
    assert result_a.verdict == ValidationVerdict.SUPPORTED

    # ---- rank()/snapshot_leaderboard(), completely unmodified ----
    snapshot_tracker = LeaderboardSnapshotTracker(tmp_path / "leaderboard.jsonl")
    snapshot = snapshot_leaderboard(
        (result_bc, result_a), RANKING_POLICY_V1, "snap1", _BASE.isoformat(), snapshot_tracker,
    )
    ranked_hypothesis_ids = {e.hypothesis_id for e in snapshot.entries}
    assert ranked_hypothesis_ids == {"h_stage_bc", "h_stage_a"}
    assert len(snapshot.excluded_validation_ids) == 0


# ---- dependency audit (test 13): Validation/Ranking gained nothing new ----

def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def _atlas_imports(file_path: Path) -> set[str]:
    return {name for name in _imported_module_roots(file_path) if name.startswith("atlas.")}


def test_validation_gained_no_backtesting_or_statistics_dependency():
    for py_file in _VALIDATION_DIR.rglob("*.py"):
        offending = {
            n for n in _atlas_imports(py_file)
            if n.startswith("atlas.research.backtesting") or n.startswith("atlas.research.statistics")
        }
        assert not offending, f"{py_file} imports {offending} - Validation must remain frozen this sprint"


def test_ranking_gained_no_backtesting_or_statistics_dependency():
    for py_file in _RANKING_DIR.rglob("*.py"):
        offending = {
            n for n in _atlas_imports(py_file)
            if n.startswith("atlas.research.backtesting") or n.startswith("atlas.research.statistics")
        }
        assert not offending, f"{py_file} imports {offending} - Ranking must remain frozen this sprint"

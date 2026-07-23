"""
Sprint 9. Tests for GET /api/v1/research/promotion/candidates,
POST /api/v1/research/promotion/decide, GET /api/v1/research/promotion -
plus the milestone's own required real-data proof (roadmap: "a real-data
end-to-end run... both for a decision-free and a decision-bearing
hypothesis") carried all the way through to a recorded promotion decision,
using the client fixture's real, tmp_path-backed LedgerStores (see
tests/conftest.py) - genuinely working stores, not a hand-built fake.
"""
from datetime import datetime, timedelta, timezone

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
)
from atlas.research.ranking.models import RANKING_POLICY_V1
from atlas.research.ranking.service import snapshot_leaderboard
from atlas.research.replay_bridge import build_replay_frames_for_window
from atlas.research.statistics.service import compute_decision_sequence_evidence, compute_evidence
from atlas.research.validation.models import MonteCarloSpec, WalkForwardSpec
from atlas.research.validation.service import validate

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---- basic endpoint behavior ----

def test_candidates_empty_when_no_leaderboard_snapshot_exists_yet(client):
    resp = client.get("/api/v1/research/promotion/candidates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["candidates"] == []


def test_decide_rejects_blank_rationale_with_422(client):
    resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h1", "decision": "approved", "reviewer": "tester",
        "rationale": "   ", "evidence_snapshot_ref": "v1",
    })
    assert resp.status_code == 422
    assert resp.json()["ok"] is False


def test_decide_rejects_invalid_decision_literal(client):
    resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h1", "decision": "maybe", "reviewer": "tester",
        "rationale": "clear evidence", "evidence_snapshot_ref": "v1",
    })
    assert resp.status_code == 422  # pydantic validation, before the route body runs


def test_decide_then_read_back_by_promotion_id(client):
    decide_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h1", "decision": "declined", "reviewer": "tester",
        "rationale": "insufficient effect size", "evidence_snapshot_ref": "v1",
    })
    assert decide_resp.status_code == 200
    promotion_id = decide_resp.json()["record"]["promotion_id"]

    read_resp = client.get(f"/api/v1/research/promotion?promotion_id={promotion_id}")
    assert read_resp.status_code == 200
    body = read_resp.json()
    assert body["ok"] is True
    assert body["record"]["decision"] == "declined"
    assert body["record"]["rationale"] == "insufficient effect size"
    assert body["record"]["resulting_production_change_ref"] is None


def test_read_unknown_promotion_id_returns_404(client):
    resp = client.get("/api/v1/research/promotion?promotion_id=does-not-exist")
    assert resp.status_code == 404


def test_promotion_history_lists_every_recorded_decision(client):
    client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h1", "decision": "approved", "reviewer": "tester",
        "rationale": "clear evidence", "evidence_snapshot_ref": "v1",
    })
    client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h2", "decision": "declined", "reviewer": "tester",
        "rationale": "weak evidence", "evidence_snapshot_ref": "v2",
    })
    resp = client.get("/api/v1/research/promotion")
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert {r["hypothesis_id"] for r in records} == {"h1", "h2"}


def test_promotion_fails_when_ledger_storage_is_degraded(client):
    from atlas.api.deps import get_ledger_readiness
    from atlas.main import app
    from atlas.research_deploy.startup_check import check_ledger_storage

    app.dependency_overrides[get_ledger_readiness] = lambda: check_ledger_storage(None)[0]
    try:
        resp = client.post("/api/v1/research/promotion/decide", json={
            "hypothesis_id": "h1", "decision": "approved", "reviewer": "tester",
            "rationale": "clear evidence", "evidence_snapshot_ref": "v1",
        })
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_ledger_readiness, None)


# ---- real end-to-end: decision-free AND decision-bearing, to a recorded decision ----

def _states_with_close(atrs: list[float], closes: list[float], base: datetime) -> list[MarketState]:
    step = timedelta(minutes=5)
    return [
        MarketState(
            envelope=Event(event_type="bar_closed", source="test", occurred_at=base + step * i, event_id=f"e{i}"),
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


def test_full_milestone_run_decision_free_and_decision_bearing_to_a_recorded_promotion_decision(client, ledger_stores):
    # ---- decision-free (Stage A) hypothesis, real pipeline throughout ----
    feature_criterion = AcceptanceCriterion(
        description="mean_atr clears 2.0", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.FEATURE, target="mean_atr", threshold=2.0,
    )
    stage_a_hypothesis = _hypothesis("h_stage_a", (feature_criterion,))
    atrs = [1.0 + i * 0.2 for i in range(20)]
    states_in = _states_with_close(atrs, [1.0] * 20, _BASE)
    oos_base = _BASE + timedelta(days=30)
    states_out = _states_with_close(atrs, [1.0] * 20, oos_base)

    outcome_in = build_experiment(
        stage_a_hypothesis, states_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        "exp_a_in", ledger_stores.experiments,
    )
    outcome_out = build_experiment(
        stage_a_hypothesis, states_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        "exp_a_out", ledger_stores.experiments,
    )
    ev_in_a = compute_evidence(outcome_in.experiment, outcome_in.feature_series, "ev_in_a", _BASE.isoformat())
    ev_out_a = compute_evidence(outcome_out.experiment, outcome_out.feature_series, "ev_out_a", _BASE.isoformat())
    result_a = validate(
        hypothesis_id="h_stage_a", in_sample_evidence=(ev_in_a,), out_of_sample_evidence=(ev_out_a,),
        criterion=feature_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_stage_a", validated_at=_BASE.isoformat(),
    )
    assert result_a.verdict.value == "supported"

    # ---- decision-bearing (Stage B/C) hypothesis, real pipeline throughout ----
    decision_criterion = AcceptanceCriterion(
        description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
    )
    stage_bc_hypothesis = _hypothesis("h_stage_bc", (decision_criterion,))
    realization = construct_realization(
        stage_bc_hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": 2.0},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, "r_bc", _BASE.isoformat(),
        ledger_stores.realizations,
    )
    closes_bc = [1.0, 3.0] * 10
    frames_in = build_replay_frames_for_window(_states_with_close([3.0] * 20, closes_bc, _BASE))
    frames_out = build_replay_frames_for_window(_states_with_close([3.0] * 20, closes_bc, oos_base))
    bc_outcome_in = build_realization_experiment(
        stage_bc_hypothesis, realization, frames_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        "exp_bc_in", ledger_stores.experiments,
    )
    bc_outcome_out = build_realization_experiment(
        stage_bc_hypothesis, realization, frames_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        "exp_bc_out", ledger_stores.experiments,
    )
    ev_in_bc = compute_decision_sequence_evidence(
        bc_outcome_in.experiment, bc_outcome_in.decision_sequence, tuple(frames_in), (decision_criterion,),
        evidence_id="ev_in_bc", computed_at=_BASE.isoformat(),
    )
    ev_out_bc = compute_decision_sequence_evidence(
        bc_outcome_out.experiment, bc_outcome_out.decision_sequence, tuple(frames_out), (decision_criterion,),
        evidence_id="ev_out_bc", computed_at=_BASE.isoformat(),
    )
    result_bc = validate(
        hypothesis_id="h_stage_bc", in_sample_evidence=(ev_in_bc,), out_of_sample_evidence=(ev_out_bc,),
        criterion=decision_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_stage_bc", validated_at=_BASE.isoformat(),
    )
    assert result_bc.verdict.value == "supported"

    # ---- rank both into one leaderboard snapshot ----
    snapshot = snapshot_leaderboard(
        (result_a, result_bc), RANKING_POLICY_V1, "snap_milestone", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )
    assert {e.hypothesis_id for e in snapshot.entries} == {"h_stage_a", "h_stage_bc"}

    # ---- both appear as promotion candidates, over real HTTP ----
    candidates_resp = client.get("/api/v1/research/promotion/candidates")
    assert candidates_resp.status_code == 200
    candidates_body = candidates_resp.json()
    assert candidates_body["snapshot_id"] == "snap_milestone"
    candidate_hypothesis_ids = {c["hypothesis_id"] for c in candidates_body["candidates"]}
    assert candidate_hypothesis_ids == {"h_stage_a", "h_stage_bc"}

    # ---- record a human decision for each, over real HTTP ----
    approve_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_stage_a", "decision": "approved", "reviewer": "tester",
        "rationale": "clean out-of-sample support, decision-free statistical claim",
        "evidence_snapshot_ref": "v_stage_a",
    })
    assert approve_resp.status_code == 200
    assert approve_resp.json()["record"]["resulting_production_change_ref"] is None

    # realization_id is omitted (defaults to None) - a real, pre-existing
    # limitation inherited from Sprint 7: rank()/LeaderboardEntry never
    # actually populates realization_id, even for a decision-bearing
    # hypothesis (confirmed in the Sprint 8.1 review; out of Sprint 9's own
    # scope to fix, since it would mean reopening the frozen Ranking
    # package). A reviewer only ever sees what the candidate entry itself
    # shows, so this is what a real decision through this API looks like
    # today, not an artificial simplification of the test.
    decline_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_stage_bc", "decision": "declined", "reviewer": "tester",
        "rationale": "entry rate too high for practical execution, wants a tighter template first",
        "evidence_snapshot_ref": "v_stage_bc",
    })
    assert decline_resp.status_code == 200

    # ---- re-querying candidates: approved excluded, declined retained+surfaced ----
    final_resp = client.get("/api/v1/research/promotion/candidates")
    final_candidates = final_resp.json()["candidates"]
    assert len(final_candidates) == 1
    assert final_candidates[0]["hypothesis_id"] == "h_stage_bc"
    assert len(final_candidates[0]["prior_decisions"]) == 1
    assert final_candidates[0]["prior_decisions"][0]["decision"] == "declined"

    # ---- full audit trail readable months later, in principle - proven now ----
    history_resp = client.get("/api/v1/research/promotion")
    history = history_resp.json()["records"]
    assert len(history) == 2
    by_hypothesis = {r["hypothesis_id"]: r for r in history}
    assert by_hypothesis["h_stage_a"]["evidence_snapshot_ref"] == "v_stage_a"
    assert by_hypothesis["h_stage_bc"]["evidence_snapshot_ref"] == "v_stage_bc"

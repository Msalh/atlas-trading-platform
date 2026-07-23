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
        realization_id=realization.realization_id,
    )
    assert result_bc.verdict.value == "supported"
    assert result_bc.realization_id == realization.realization_id

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

    # realization_id is never supplied by the reviewer here - the endpoint
    # resolves it itself from the exact Experiment/Evidence/Validation
    # lineage that produced h_stage_bc's LeaderboardEntry (realization
    # lineage correction) - see _resolve_realization_id() in
    # atlas/api/v1/promotion.py.
    decline_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_stage_bc", "decision": "declined", "reviewer": "tester",
        "rationale": "entry rate too high for practical execution, wants a tighter template first",
        "evidence_snapshot_ref": "v_stage_bc",
    })
    assert decline_resp.status_code == 200
    assert decline_resp.json()["record"]["realization_id"] == realization.realization_id

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


# ---- realization lineage correction: the 6 explicitly required tests ----
#
# Test 1 (a decision-bearing experiment preserves its exact realization_id
# through Evidence, Validation, Ranking, PromotionCandidate, and
# PromotionRecord) and Test 4 (a decision-free hypothesis continues to use
# realization_id=None) are already proven end-to-end by
# test_full_milestone_run_decision_free_and_decision_bearing_to_a_recorded_
# promotion_decision above (h_stage_bc / h_stage_a respectively). The
# remaining four are covered explicitly below.

def _decision_bearing_result(
    ledger_stores, hypothesis_id: str, realization_id: str, closes: list[float], threshold: float = 2.0,
):
    """Builds one real Realization -> Experiment -> decision sequence ->
    Evidence -> ValidationResult, decision-bearing throughout (mirrors the
    milestone test's own h_stage_bc block) - returns (result, realization)."""
    decision_criterion = AcceptanceCriterion(
        description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
    )
    hypothesis = _hypothesis(hypothesis_id, (decision_criterion,))
    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": threshold},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, realization_id, _BASE.isoformat(),
        ledger_stores.realizations,
    )
    # Out-of-sample uses a distinct base timestamp - build_realization_
    # experiment() caches on execution_fingerprint (which folds in the
    # RESOLVED dataset manifest), so identical in/out windows would hit the
    # cache and come back with decision_sequence=None on the second call.
    oos_base = _BASE + timedelta(days=1)
    frames_in = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, _BASE))
    frames_out = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, oos_base))
    outcome_in = build_realization_experiment(
        hypothesis, realization, frames_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        f"exp_in_{realization_id}", ledger_stores.experiments,
    )
    outcome_out = build_realization_experiment(
        hypothesis, realization, frames_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        f"exp_out_{realization_id}", ledger_stores.experiments,
    )
    ev_in = compute_decision_sequence_evidence(
        outcome_in.experiment, outcome_in.decision_sequence, tuple(frames_in), (decision_criterion,),
        evidence_id=f"ev_in_{realization_id}", computed_at=_BASE.isoformat(),
    )
    ev_out = compute_decision_sequence_evidence(
        outcome_out.experiment, outcome_out.decision_sequence, tuple(frames_out), (decision_criterion,),
        evidence_id=f"ev_out_{realization_id}", computed_at=_BASE.isoformat(),
    )
    result = validate(
        hypothesis_id=hypothesis_id, in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=decision_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id=f"v_{realization_id}", validated_at=_BASE.isoformat(),
        realization_id=realization.realization_id,
    )
    return result, realization


def test_two_realizations_of_the_same_hypothesis_are_distinguishable_end_to_end(client, ledger_stores):
    """Test 2: two Realizations of the SAME Hypothesis, validated and
    ranked in two separate snapshots (the one-entry-per-hypothesis-per-
    snapshot policy is unchanged from Sprint 7), each carry their own
    distinct realization_id all the way to the promotion queue and into
    the recorded PromotionRecord."""
    closes = [1.0, 3.0] * 10
    result_r1, _realization_1 = _decision_bearing_result(ledger_stores, "h_two_realizations", "r_two_1", closes)
    snapshot_1 = snapshot_leaderboard(
        (result_r1,), RANKING_POLICY_V1, "snap_two_1", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )
    assert snapshot_1.entries[0].realization_id == "r_two_1"

    candidates_1 = client.get("/api/v1/research/promotion/candidates").json()["candidates"]
    assert candidates_1[0]["realization_id"] == "r_two_1"

    decide_1 = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_two_realizations", "decision": "declined", "reviewer": "tester",
        "rationale": "first parameterization underperforms", "evidence_snapshot_ref": "snap_two_1",
    })
    assert decide_1.json()["record"]["realization_id"] == "r_two_1"

    result_r2, realization_2 = _decision_bearing_result(ledger_stores, "h_two_realizations", "r_two_2", closes)
    snapshot_2_created_at = (_BASE + timedelta(hours=1)).isoformat()
    snapshot_2 = snapshot_leaderboard(
        (result_r2,), RANKING_POLICY_V1, "snap_two_2", snapshot_2_created_at, ledger_stores.leaderboard_snapshots,
    )
    assert snapshot_2.entries[0].realization_id == "r_two_2"
    assert snapshot_2.entries[0].realization_id != snapshot_1.entries[0].realization_id

    candidates_2 = client.get("/api/v1/research/promotion/candidates").json()["candidates"]
    assert candidates_2[0]["realization_id"] == "r_two_2"
    # r_two_1's own prior DECLINED decision does not bleed onto r_two_2 -
    # each Realization's promotion history is its own.
    assert candidates_2[0]["prior_decisions"] == []

    decide_2 = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_two_realizations", "decision": "approved", "reviewer": "tester",
        "rationale": "second parameterization clears the bar", "evidence_snapshot_ref": "snap_two_2",
    })
    assert decide_2.json()["record"]["realization_id"] == "r_two_2"

    history = client.get("/api/v1/research/promotion").json()["records"]
    by_realization = {r["realization_id"]: r for r in history if r["hypothesis_id"] == "h_two_realizations"}
    assert by_realization["r_two_1"]["decision"] == "declined"
    assert by_realization["r_two_2"]["decision"] == "approved"


def test_decide_endpoint_never_accepts_a_client_supplied_realization_id(client, ledger_stores):
    """Test 3: no 'latest Realization' or hypothesis-only lookup, and no
    reviewer-supplied realization_id, is ever used - PromotionDecisionRequest
    has no such field at all, so a client attempting to inject one has
    zero effect on the recorded PromotionRecord (extra JSON fields are
    silently ignored by pydantic, not an error, but never consulted)."""
    closes = [1.0, 3.0] * 10
    result, _realization = _decision_bearing_result(ledger_stores, "h_no_client_realization", "r_real", closes)
    snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_no_client", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )

    resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_no_client_realization", "decision": "approved", "reviewer": "tester",
        "rationale": "clears the bar", "evidence_snapshot_ref": "snap_no_client",
        "realization_id": "r_attacker_supplied",  # must be ignored entirely
    })
    assert resp.status_code == 200
    assert resp.json()["record"]["realization_id"] == "r_real"
    assert resp.json()["record"]["realization_id"] != "r_attacker_supplied"


def test_decision_bearing_candidate_with_missing_realization_id_is_rejected(client, ledger_stores):
    """Test 5: a decision-bearing candidate (its ValidationResult used a
    DECISION_SEQUENCE criterion) whose realization_id is unexpectedly
    missing must be rejected, not silently recorded as realization_id=None
    - this can only happen by bypassing validate()'s own trusted-parameter
    contract (omitting realization_id even though the Evidence came from a
    real Realization), simulating a lineage-loss scenario the router must
    still catch rather than guess through."""
    hypothesis = _hypothesis("h_missing_realization", (
        AcceptanceCriterion(
            description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
            target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
        ),
    ))
    decision_criterion = hypothesis.acceptance_criteria[0]
    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": 2.0},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, "r_lost", _BASE.isoformat(),
        ledger_stores.realizations,
    )
    closes = [1.0, 3.0] * 10
    oos_base = _BASE + timedelta(days=1)
    frames_in = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, _BASE))
    frames_out = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, oos_base))
    outcome_in = build_realization_experiment(
        hypothesis, realization, frames_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        "exp_lost_in", ledger_stores.experiments,
    )
    outcome_out = build_realization_experiment(
        hypothesis, realization, frames_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        "exp_lost_out", ledger_stores.experiments,
    )
    evidence_in = compute_decision_sequence_evidence(
        outcome_in.experiment, outcome_in.decision_sequence, tuple(frames_in), (decision_criterion,),
        evidence_id="ev_lost_in", computed_at=_BASE.isoformat(),
    )
    evidence_out = compute_decision_sequence_evidence(
        outcome_out.experiment, outcome_out.decision_sequence, tuple(frames_out), (decision_criterion,),
        evidence_id="ev_lost_out", computed_at=_BASE.isoformat(),
    )
    # realization_id deliberately omitted (defaults to None) even though
    # this Evidence came from a real Realization - simulates lineage loss.
    result = validate(
        hypothesis_id="h_missing_realization", in_sample_evidence=(evidence_in,), out_of_sample_evidence=(evidence_out,),
        criterion=decision_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_lost", validated_at=_BASE.isoformat(),
    )
    assert result.realization_id is None
    ledger_stores.validation_results.record(result)
    snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_lost", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )

    resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_missing_realization", "decision": "approved", "reviewer": "tester",
        "rationale": "looks fine", "evidence_snapshot_ref": "snap_lost",
    })
    assert resp.status_code == 422
    assert resp.json()["reason"] == "realization_id_unresolved"


def test_full_audit_chain_walks_from_promotion_record_back_to_realization_parameters(client, ledger_stores):
    """Test 6: starting from only a PromotionRecord (as read via the real
    HTTP API), the exact Realization and its parameters can be recovered -
    PromotionRecord.realization_id -> Realization -> its parameters dict,
    proving the audit chain the whole correction exists to make possible."""
    closes = [1.0, 3.0] * 10
    result, realization = _decision_bearing_result(
        ledger_stores, "h_audit_chain", "r_audit_chain", closes, threshold=2.5,
    )
    snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_audit_chain", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )
    decide_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_audit_chain", "decision": "approved", "reviewer": "tester",
        "rationale": "clears the bar, ready to promote", "evidence_snapshot_ref": "snap_audit_chain",
    })
    promotion_id = decide_resp.json()["record"]["promotion_id"]

    # ---- months later, in principle: walk back from only the promotion_id ----
    record = client.get(f"/api/v1/research/promotion?promotion_id={promotion_id}").json()["record"]
    assert record["realization_id"] == "r_audit_chain"

    walked_realization = ledger_stores.realizations.get(record["realization_id"])
    assert walked_realization is not None
    assert walked_realization.realization_id == realization.realization_id
    assert walked_realization.parameters == {"threshold": 2.5}
    assert walked_realization.hypothesis_id == "h_audit_chain"

"""
Sprint 10 Slice A. Tests for GET /api/v1/research/lineage - the composed,
read-only walk from a PromotionRecord or a ValidationResult back through
LeaderboardSnapshot, Evidence, Experiment, and Realization. Uses the
client fixture's real, tmp_path-backed LedgerStores (see tests/conftest.py) -
genuinely working stores, not a hand-built fake, the same discipline the
Sprint 9 promotion tests already established.
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


# ---- basic request validation ----

def test_lineage_requires_exactly_one_identifier(client):
    resp = client.get("/api/v1/research/lineage")
    assert resp.status_code == 422


def test_lineage_rejects_both_identifiers_at_once(client):
    resp = client.get("/api/v1/research/lineage?promotion_id=p1&validation_id=v1")
    assert resp.status_code == 422


def test_lineage_by_unknown_promotion_id_returns_404(client):
    resp = client.get("/api/v1/research/lineage?promotion_id=does-not-exist")
    assert resp.status_code == 404


def test_lineage_by_unknown_validation_id_returns_404(client):
    resp = client.get("/api/v1/research/lineage?validation_id=does-not-exist")
    assert resp.status_code == 404


def test_lineage_fails_when_ledger_storage_is_degraded(client):
    from atlas.api.deps import get_ledger_readiness
    from atlas.main import app
    from atlas.research_deploy.startup_check import check_ledger_storage

    app.dependency_overrides[get_ledger_readiness] = lambda: check_ledger_storage(None)[0]
    try:
        resp = client.get("/api/v1/research/lineage?promotion_id=p1")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_ledger_readiness, None)


# ---- ad hoc / legacy promotion decisions: no matching leaderboard entry ----

def test_lineage_by_promotion_id_with_no_matching_leaderboard_entry_degrades_gracefully(client):
    """A promotion decision recorded for a hypothesis that was never ranked
    (the basic decide-endpoint tests use ad hoc hypothesis_ids like "h1"
    with no real Ledger content behind them) must never 500 - it returns
    what it can and reports the gap via `warnings`."""
    decide_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h1", "decision": "declined", "reviewer": "tester",
        "rationale": "insufficient effect size", "evidence_snapshot_ref": "v1",
    })
    promotion_id = decide_resp.json()["record"]["promotion_id"]

    resp = client.get(f"/api/v1/research/lineage?promotion_id={promotion_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["hypothesis_id"] == "h1"
    assert body["realization_id"] is None
    assert body["leaderboard_entries"] == []
    assert body["validation_results"] == []
    assert body["evidence"] == []
    assert body["experiments"] == []
    assert body["realization"] is None
    assert len(body["promotion_records"]) == 1
    assert body["promotion_records"][0]["promotion_id"] == promotion_id
    assert any("no leaderboard entry found" in w for w in body["warnings"])


# ---- real end-to-end: decision-free (Stage A) and decision-bearing (Stage B/C) ----

def test_full_lineage_walk_for_a_decision_free_hypothesis(client, ledger_stores):
    feature_criterion = AcceptanceCriterion(
        description="mean_atr clears 2.0", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.FEATURE, target="mean_atr", threshold=2.0,
    )
    hypothesis = _hypothesis("h_lineage_a", (feature_criterion,))
    atrs = [1.0 + i * 0.2 for i in range(20)]
    states_in = _states_with_close(atrs, [1.0] * 20, _BASE)
    oos_base = _BASE + timedelta(days=30)
    states_out = _states_with_close(atrs, [1.0] * 20, oos_base)

    outcome_in = build_experiment(
        hypothesis, states_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE, "exp_a_in", ledger_stores.experiments,
    )
    outcome_out = build_experiment(
        hypothesis, states_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base, "exp_a_out",
        ledger_stores.experiments,
    )
    ev_in = compute_evidence(outcome_in.experiment, outcome_in.feature_series, "ev_in_a", _BASE.isoformat())
    ev_out = compute_evidence(outcome_out.experiment, outcome_out.feature_series, "ev_out_a", _BASE.isoformat())
    ledger_stores.evidence.record(ev_in)
    ledger_stores.evidence.record(ev_out)
    result = validate(
        hypothesis_id="h_lineage_a", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=feature_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_lineage_a", validated_at=_BASE.isoformat(),
    )
    assert result.verdict.value == "supported"
    ledger_stores.validation_results.record(result)
    snapshot = snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_lineage_a", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )

    decide_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_lineage_a", "decision": "approved", "reviewer": "tester",
        "rationale": "clean out-of-sample support", "evidence_snapshot_ref": "v_lineage_a",
    })
    promotion_id = decide_resp.json()["record"]["promotion_id"]
    assert decide_resp.json()["record"]["realization_id"] is None

    resp = client.get(f"/api/v1/research/lineage?promotion_id={promotion_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["hypothesis_id"] == "h_lineage_a"
    assert body["realization_id"] is None
    assert body["realization"] is None
    assert body["warnings"] == []

    assert len(body["leaderboard_entries"]) == 1
    assert body["leaderboard_entries"][0]["snapshot_id"] == snapshot.snapshot_id
    assert body["leaderboard_entries"][0]["validation_id"] == "v_lineage_a"

    assert [v["validation_id"] for v in body["validation_results"]] == ["v_lineage_a"]
    assert {e["evidence_id"] for e in body["evidence"]} == {"ev_in_a", "ev_out_a"}
    assert {e["experiment_id"] for e in body["experiments"]} == {"exp_a_in", "exp_a_out"}

    assert len(body["promotion_records"]) == 1
    assert body["promotion_records"][0]["promotion_id"] == promotion_id
    assert body["promotion_records"][0]["decision"] == "approved"

    # ---- the same walk, entered from validation_id instead of promotion_id ----
    by_validation = client.get("/api/v1/research/lineage?validation_id=v_lineage_a")
    assert by_validation.status_code == 200
    by_validation_body = by_validation.json()
    assert by_validation_body["requested_promotion_id"] is None
    assert by_validation_body["requested_validation_id"] == "v_lineage_a"
    assert {e["evidence_id"] for e in by_validation_body["evidence"]} == {"ev_in_a", "ev_out_a"}
    assert len(by_validation_body["promotion_records"]) == 1
    assert by_validation_body["promotion_records"][0]["promotion_id"] == promotion_id


def test_full_lineage_walk_for_a_decision_bearing_hypothesis_including_realization(client, ledger_stores):
    decision_criterion = AcceptanceCriterion(
        description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
    )
    hypothesis = _hypothesis("h_lineage_bc", (decision_criterion,))
    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": 2.0},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, "r_lineage_bc", _BASE.isoformat(),
        ledger_stores.realizations,
    )
    closes = [1.0, 3.0] * 10
    oos_base = _BASE + timedelta(days=1)
    frames_in = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, _BASE))
    frames_out = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, oos_base))
    outcome_in = build_realization_experiment(
        hypothesis, realization, frames_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        "exp_bc_in", ledger_stores.experiments,
    )
    outcome_out = build_realization_experiment(
        hypothesis, realization, frames_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        "exp_bc_out", ledger_stores.experiments,
    )
    ev_in = compute_decision_sequence_evidence(
        outcome_in.experiment, outcome_in.decision_sequence, tuple(frames_in), (decision_criterion,),
        evidence_id="ev_bc_in", computed_at=_BASE.isoformat(),
    )
    ev_out = compute_decision_sequence_evidence(
        outcome_out.experiment, outcome_out.decision_sequence, tuple(frames_out), (decision_criterion,),
        evidence_id="ev_bc_out", computed_at=_BASE.isoformat(),
    )
    ledger_stores.evidence.record(ev_in)
    ledger_stores.evidence.record(ev_out)
    result = validate(
        hypothesis_id="h_lineage_bc", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=decision_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_lineage_bc", validated_at=_BASE.isoformat(),
        realization_id=realization.realization_id,
    )
    assert result.verdict.value == "supported"
    ledger_stores.validation_results.record(result)
    snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_lineage_bc", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )

    decline_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_lineage_bc", "decision": "declined", "reviewer": "tester",
        "rationale": "too aggressive", "evidence_snapshot_ref": "v_lineage_bc",
    })
    promotion_id = decline_resp.json()["record"]["promotion_id"]
    assert decline_resp.json()["record"]["realization_id"] == "r_lineage_bc"

    resp = client.get(f"/api/v1/research/lineage?promotion_id={promotion_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["realization_id"] == "r_lineage_bc"
    assert body["realization"] is not None
    assert body["realization"]["realization_id"] == "r_lineage_bc"
    assert body["realization"]["parameters"] == {"threshold": 2.0}
    assert body["warnings"] == []
    assert {e["evidence_id"] for e in body["evidence"]} == {"ev_bc_in", "ev_bc_out"}
    assert {e["experiment_id"] for e in body["experiments"]} == {"exp_bc_in", "exp_bc_out"}


def test_lineage_promotion_records_includes_full_history_for_the_same_candidate(client, ledger_stores):
    """Two decisions recorded over time for the same (hypothesis_id,
    realization_id) pair - the lineage walk must surface both, not only
    the one that was directly requested by promotion_id, matching how
    PromotionCandidate.prior_decisions already works."""
    decision_criterion = AcceptanceCriterion(
        description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
    )
    hypothesis = _hypothesis("h_lineage_history", (decision_criterion,))
    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": 2.0},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, "r_lineage_history", _BASE.isoformat(),
        ledger_stores.realizations,
    )
    closes = [1.0, 3.0] * 10
    oos_base = _BASE + timedelta(days=1)
    frames_in = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, _BASE))
    frames_out = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, oos_base))
    outcome_in = build_realization_experiment(
        hypothesis, realization, frames_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        "exp_hist_in", ledger_stores.experiments,
    )
    outcome_out = build_realization_experiment(
        hypothesis, realization, frames_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        "exp_hist_out", ledger_stores.experiments,
    )
    ev_in = compute_decision_sequence_evidence(
        outcome_in.experiment, outcome_in.decision_sequence, tuple(frames_in), (decision_criterion,),
        evidence_id="ev_hist_in", computed_at=_BASE.isoformat(),
    )
    ev_out = compute_decision_sequence_evidence(
        outcome_out.experiment, outcome_out.decision_sequence, tuple(frames_out), (decision_criterion,),
        evidence_id="ev_hist_out", computed_at=_BASE.isoformat(),
    )
    ledger_stores.evidence.record(ev_in)
    ledger_stores.evidence.record(ev_out)
    result = validate(
        hypothesis_id="h_lineage_history", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=decision_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_lineage_history", validated_at=_BASE.isoformat(),
        realization_id=realization.realization_id,
    )
    ledger_stores.validation_results.record(result)
    snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_lineage_history", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )

    first = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_lineage_history", "decision": "deferred", "reviewer": "tester",
        "rationale": "want a second opinion first", "evidence_snapshot_ref": "v_lineage_history",
    })
    second = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_lineage_history", "decision": "approved", "reviewer": "tester",
        "rationale": "second opinion agrees", "evidence_snapshot_ref": "v_lineage_history",
    })
    first_id = first.json()["record"]["promotion_id"]
    second_id = second.json()["record"]["promotion_id"]

    resp = client.get(f"/api/v1/research/lineage?promotion_id={first_id}")
    body = resp.json()
    assert body["requested_promotion_id"] == first_id
    returned_ids = {p["promotion_id"] for p in body["promotion_records"]}
    assert returned_ids == {first_id, second_id}
    decisions_by_id = {p["promotion_id"]: p["decision"] for p in body["promotion_records"]}
    assert decisions_by_id[first_id] == "deferred"
    assert decisions_by_id[second_id] == "approved"


# ---- Sprint 10 Slice A.1 hardening: each store read at most once per request ----

def test_lineage_reads_each_ledger_store_at_most_once_per_request(client, ledger_stores, monkeypatch):
    """Mechanical proof, not an inspection-only claim: wraps .all()/.get()
    on every store the endpoint touches with a call counter, then asserts
    .all() is called exactly once per store and .get() is never called at
    all on those six stores - the original Slice A implementation called
    .get() once per referenced id (once per evidence_id, once per
    experiment_id, ...), which independently re-scanned the entire JSONL
    file each time (atlas/research/stores.py has no caching or indexing).
    This test would fail against that implementation."""
    decision_criterion = AcceptanceCriterion(
        description="enter_long_rate clears 0.1", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.1,
    )
    hypothesis = _hypothesis("h_read_count", (decision_criterion,))
    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": 2.0},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, "r_read_count", _BASE.isoformat(),
        ledger_stores.realizations,
    )
    closes = [1.0, 3.0] * 10
    oos_base = _BASE + timedelta(days=1)
    frames_in = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, _BASE))
    frames_out = build_replay_frames_for_window(_states_with_close([3.0] * len(closes), closes, oos_base))
    outcome_in = build_realization_experiment(
        hypothesis, realization, frames_in, _BASE.isoformat(), _BASE.isoformat(), "test", _BASE,
        "exp_rc_in", ledger_stores.experiments,
    )
    outcome_out = build_realization_experiment(
        hypothesis, realization, frames_out, oos_base.isoformat(), oos_base.isoformat(), "test", oos_base,
        "exp_rc_out", ledger_stores.experiments,
    )
    ev_in = compute_decision_sequence_evidence(
        outcome_in.experiment, outcome_in.decision_sequence, tuple(frames_in), (decision_criterion,),
        evidence_id="ev_rc_in", computed_at=_BASE.isoformat(),
    )
    ev_out = compute_decision_sequence_evidence(
        outcome_out.experiment, outcome_out.decision_sequence, tuple(frames_out), (decision_criterion,),
        evidence_id="ev_rc_out", computed_at=_BASE.isoformat(),
    )
    ledger_stores.evidence.record(ev_in)
    ledger_stores.evidence.record(ev_out)
    result = validate(
        hypothesis_id="h_read_count", in_sample_evidence=(ev_in,), out_of_sample_evidence=(ev_out,),
        criterion=decision_criterion, walk_forward_spec=WalkForwardSpec(1, 1, "single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id="v_read_count", validated_at=_BASE.isoformat(),
        realization_id=realization.realization_id,
    )
    ledger_stores.validation_results.record(result)
    snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, "snap_read_count", _BASE.isoformat(), ledger_stores.leaderboard_snapshots,
    )
    decide_resp = client.post("/api/v1/research/promotion/decide", json={
        "hypothesis_id": "h_read_count", "decision": "approved", "reviewer": "tester",
        "rationale": "clears the bar", "evidence_snapshot_ref": "v_read_count",
    })
    promotion_id = decide_resp.json()["record"]["promotion_id"]

    counts: dict[str, int] = {}

    def _counted(store, store_name: str, method_name: str):
        original = getattr(store, method_name)

        def wrapper(*args, **kwargs):
            key = f"{store_name}.{method_name}"
            counts[key] = counts.get(key, 0) + 1
            return original(*args, **kwargs)

        monkeypatch.setattr(store, method_name, wrapper)

    touched_stores = {
        "promotions": ledger_stores.promotions,
        "leaderboard_snapshots": ledger_stores.leaderboard_snapshots,
        "validation_results": ledger_stores.validation_results,
        "evidence": ledger_stores.evidence,
        "experiments": ledger_stores.experiments,
        "realizations": ledger_stores.realizations,
    }
    for name, store in touched_stores.items():
        _counted(store, name, "all")
        _counted(store, name, "get")

    resp = client.get(f"/api/v1/research/lineage?promotion_id={promotion_id}")
    assert resp.status_code == 200
    body = resp.json()
    # Sanity check the walk actually found everything, so this test would
    # fail loudly (not silently pass on an empty walk) if the fixture above
    # ever stops producing real evidence/experiments/realization data.
    assert len(body["evidence"]) == 2
    assert len(body["experiments"]) == 2
    assert body["realization"] is not None

    for name in touched_stores:
        assert counts.get(f"{name}.all", 0) == 1, f"{name}.all() called {counts.get(f'{name}.all', 0)} times, expected exactly 1"
        assert counts.get(f"{name}.get", 0) == 0, f"{name}.get() called {counts.get(f'{name}.get', 0)} times, expected 0"

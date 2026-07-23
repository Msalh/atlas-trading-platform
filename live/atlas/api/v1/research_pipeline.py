"""
Sprint 8.2 (Railway Staging Deployment). POST /api/v1/research/run and
GET /api/v1/research/leaderboard - the two endpoints the Sprint 8.2
architectural review concluded staging actually needs, nothing more.

POST /research/run takes an explicit `mode` rather than being named
smoke-test-only, so future sprints can extend the same endpoint with
"replay"/"experiment"/"benchmark" without replacing the API surface (a
refinement requested during review). Only "smoke" is implemented this
sprint; every other mode returns a stable 501, never a 404/422 that could
be confused with a client error.

The smoke test proves persistence, not only computation (a second
requested refinement): every stage - Realization, both Experiments,
both Evidence records, the ValidationResult, the LeaderboardSnapshot -
is verified by reading it back from the real, Volume-backed Ledger stores
immediately after writing it, never merely "no exception was raised."
Statistics's/Validation's own pure, no-I/O boundary (unchanged, frozen
since Sprint 5/6) means this router - not atlas.research.statistics or
atlas.research.validation - is responsible for persisting Evidence/
ValidationResult via the EvidenceTracker/ValidationResultTracker that have
existed, unused by any real caller, since Sprint 2.

Uses a self-contained, deterministic synthetic dataset - never touches
Postgres/market_state - so the smoke test's pass/fail is governed only by
"did the research pipeline and Ledger Volume work," not confounded by
whether Postgres happens to be seeded with real data yet. Every entity id
is suffixed with a per-request token, so repeated calls (e.g. on every
deploy verification) never collide with a prior run's records.

Protected by the same shared API_KEY every other authenticated router in
this app uses (applied at router-registration time in atlas/main.py).
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from atlas.api.deps import get_ledger_readiness, get_ledger_stores
from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.experiment_builder.service import build_realization_experiment, construct_realization
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
from atlas.research.statistics.service import compute_decision_sequence_evidence
from atlas.research.validation.models import MonteCarloSpec, WalkForwardSpec
from atlas.research.validation.service import validate
from atlas.research_deploy.startup_check import LedgerReadiness, LedgerStores

router = APIRouter()

_RUN_MODES = ("smoke", "replay", "experiment", "benchmark")
_IMPLEMENTED_MODES = ("smoke",)

_SMOKE_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_SMOKE_CLOSES_IN_SAMPLE = [1.0, 3.0] * 10   # crosses the threshold repeatedly - a known SUPPORTED shape
_SMOKE_CLOSES_OUT_OF_SAMPLE = [1.0, 3.0] * 10
_SMOKE_THRESHOLD = 2.0
_SMOKE_RATE_THRESHOLD = 0.1
_SMOKE_TARGET = "enter_long_rate"


class ResearchRunRequest(BaseModel):
    mode: Literal["smoke", "replay", "experiment", "benchmark"]


def _degraded_response(readiness: LedgerReadiness) -> Optional[JSONResponse]:
    if readiness.status == "ready":
        return None
    return JSONResponse(
        {"ok": False, "error": f"research ledger storage is degraded: {readiness.reason}", "reason": readiness.reason},
        status_code=503,
    )


def _smoke_states(closes: list[float], base: datetime) -> list[MarketState]:
    step = timedelta(minutes=5)
    return [
        MarketState(
            envelope=Event(event_type="bar_closed", source="smoke_test", occurred_at=base + step * i, event_id=f"e{i}"),
            schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
            close=Price(value=close, tick_size=0.25),
        )
        for i, close in enumerate(closes)
    ]


def _run_smoke_test(stores: LedgerStores) -> JSONResponse:
    token = uuid.uuid4().hex[:12]
    now_iso = datetime.now(timezone.utc).isoformat()
    steps: dict[str, bool] = {}
    errors: dict[str, str] = {}

    def _fail(step: str, detail: str) -> JSONResponse:
        steps[step] = False
        errors[step] = detail
        return JSONResponse({"ok": False, "mode": "smoke", "run_id": token, "steps": steps, "errors": errors}, status_code=500)

    criterion = AcceptanceCriterion(
        description="enter_long_rate clears threshold", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target=_SMOKE_TARGET, threshold=_SMOKE_RATE_THRESHOLD,
    )
    hypothesis = Hypothesis(
        hypothesis_id=f"smoke_h_{token}", registered_at=now_iso, author="staging-smoke-test",
        statement="staging deployment smoke test", dataset_symbol="MNQU6", dataset_timeframe="5m",
        dataset_start=_SMOKE_BASE.isoformat(), dataset_end=(_SMOKE_BASE + timedelta(days=1)).isoformat(),
        acceptance_criteria=(criterion,), feature_refs=(),
    )

    realization = construct_realization(
        hypothesis, RealizationKind.TEMPLATED_STRATEGY, "v1", {"threshold": _SMOKE_THRESHOLD},
        RealizationTemplateKind.THRESHOLD_CROSS, ProvenanceKind.HUMAN, f"smoke_r_{token}", now_iso,
        stores.realizations,
    )
    stored_realization = stores.realizations.get(realization.realization_id)
    if stored_realization != realization:
        return _fail("realization_stored", "realization was not found in the Ledger after registration")
    steps["realization_stored"] = True

    in_sample_frames = build_replay_frames_for_window(_smoke_states(_SMOKE_CLOSES_IN_SAMPLE, _SMOKE_BASE))
    out_of_sample_base = _SMOKE_BASE + timedelta(days=1)
    out_of_sample_frames = build_replay_frames_for_window(_smoke_states(_SMOKE_CLOSES_OUT_OF_SAMPLE, out_of_sample_base))

    outcome_in = build_realization_experiment(
        hypothesis, realization, in_sample_frames, _SMOKE_BASE.isoformat(), _SMOKE_BASE.isoformat(),
        "smoke_test", _SMOKE_BASE, f"smoke_exp_in_{token}", stores.experiments,
    )
    outcome_out = build_realization_experiment(
        hypothesis, realization, out_of_sample_frames, out_of_sample_base.isoformat(), out_of_sample_base.isoformat(),
        "smoke_test", out_of_sample_base, f"smoke_exp_out_{token}", stores.experiments,
    )
    if stores.experiments.get(outcome_in.experiment.experiment_id) != outcome_in.experiment:
        return _fail("experiment_stored", "in-sample experiment was not found in the Ledger after recording")
    if stores.experiments.get(outcome_out.experiment.experiment_id) != outcome_out.experiment:
        return _fail("experiment_stored", "out-of-sample experiment was not found in the Ledger after recording")
    steps["experiment_stored"] = True

    evidence_in = compute_decision_sequence_evidence(
        outcome_in.experiment, outcome_in.decision_sequence, tuple(in_sample_frames), (criterion,),
        evidence_id=f"smoke_ev_in_{token}", computed_at=now_iso,
    )
    evidence_out = compute_decision_sequence_evidence(
        outcome_out.experiment, outcome_out.decision_sequence, tuple(out_of_sample_frames), (criterion,),
        evidence_id=f"smoke_ev_out_{token}", computed_at=now_iso,
    )
    # Statistics is pure/no-I/O by design (frozen since Sprint 5) - this
    # router, not compute_decision_sequence_evidence(), is responsible for
    # persisting Evidence, via the EvidenceTracker that has existed since
    # Sprint 2 with no real caller until now.
    stores.evidence.record(evidence_in)
    stores.evidence.record(evidence_out)
    if stores.evidence.get(evidence_in.evidence_id) != evidence_in:
        return _fail("evidence_stored", "in-sample evidence was not found in the Ledger after recording")
    if stores.evidence.get(evidence_out.evidence_id) != evidence_out:
        return _fail("evidence_stored", "out-of-sample evidence was not found in the Ledger after recording")
    steps["evidence_stored"] = True

    result = validate(
        hypothesis_id=hypothesis.hypothesis_id, in_sample_evidence=(evidence_in,), out_of_sample_evidence=(evidence_out,),
        criterion=criterion, walk_forward_spec=WalkForwardSpec(1, 1, "smoke test single fold"),
        monte_carlo_spec=MonteCarloSpec(n_draws=2000, seed=42), batch_size=1,
        validation_id=f"smoke_v_{token}", validated_at=now_iso,
    )
    # Validation is pure/no-I/O by design (frozen since Sprint 6) - same
    # orchestration-level responsibility as Evidence above, via the
    # ValidationResultTracker that has existed since Sprint 2.
    stores.validation_results.record(result)
    if stores.validation_results.get(result.validation_id) != result:
        return _fail("validation_stored", "validation result was not found in the Ledger after recording")
    steps["validation_stored"] = True

    snapshot = snapshot_leaderboard(
        (result,), RANKING_POLICY_V1, f"smoke_snap_{token}", now_iso, stores.leaderboard_snapshots,
    )
    if stores.leaderboard_snapshots.get(snapshot.snapshot_id) != snapshot:
        return _fail("leaderboard_snapshot_stored", "leaderboard snapshot was not found in the Ledger after recording")
    steps["leaderboard_snapshot_stored"] = True

    return JSONResponse({
        "ok": True,
        "mode": "smoke",
        "run_id": token,
        "steps": steps,
        "verdict": result.verdict.value,
        "snapshot_id": snapshot.snapshot_id,
    })


@router.post("/research/run")
async def run_research(
    body: ResearchRunRequest,
    ledger_readiness: LedgerReadiness = Depends(get_ledger_readiness),
    ledger_stores: Optional[LedgerStores] = Depends(get_ledger_stores),
):
    if body.mode not in _IMPLEMENTED_MODES:
        return JSONResponse(
            {"ok": False, "mode": body.mode, "error": f"mode {body.mode!r} is not yet implemented"},
            status_code=501,
        )
    degraded = _degraded_response(ledger_readiness)
    if degraded is not None:
        return degraded
    if ledger_stores is None:
        return JSONResponse(
            {"ok": False, "error": "research ledger stores are unavailable", "reason": "internal_error"},
            status_code=503,
        )
    return _run_smoke_test(ledger_stores)


@router.get("/research/leaderboard")
async def read_leaderboard(
    snapshot_id: Optional[str] = None,
    ledger_readiness: LedgerReadiness = Depends(get_ledger_readiness),
    ledger_stores: Optional[LedgerStores] = Depends(get_ledger_stores),
):
    degraded = _degraded_response(ledger_readiness)
    if degraded is not None:
        return degraded
    if ledger_stores is None:
        return JSONResponse(
            {"ok": False, "error": "research ledger stores are unavailable", "reason": "internal_error"},
            status_code=503,
        )

    if snapshot_id is not None:
        snapshot = ledger_stores.leaderboard_snapshots.get(snapshot_id)
        if snapshot is None:
            return JSONResponse({"ok": False, "error": f"no leaderboard snapshot with id {snapshot_id!r}"}, status_code=404)
    else:
        all_snapshots = ledger_stores.leaderboard_snapshots.all()
        if not all_snapshots:
            return JSONResponse({"ok": False, "error": "no leaderboard snapshots have been recorded yet"}, status_code=404)
        snapshot = max(all_snapshots, key=lambda s: s.created_at)

    return JSONResponse({
        "ok": True,
        "snapshot_id": snapshot.snapshot_id,
        "created_at": snapshot.created_at,
        "ranking_policy_id": snapshot.ranking_policy_id,
        "ranking_policy_version": snapshot.ranking_policy_version,
        "entries": [
            {
                "hypothesis_id": e.hypothesis_id, "realization_id": e.realization_id, "rank": e.rank,
                "score": e.score, "validation_id": e.validation_id,
            }
            for e in snapshot.entries
        ],
    })

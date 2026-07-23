"""
Sprint 10 Slice A (Research Operations Integration). GET /research/lineage -
one composed, read-only walk from a PromotionRecord or a ValidationResult
back through LeaderboardSnapshot, Evidence, Experiment, and Realization -
the exact chain the realization lineage correction (Sprint 9) made
possible to prove, now exposed as a single endpoint per the Sprint 10
architecture review's own conclusion: this composition must live on the
backend, never assembled from several calls in the Next.js BFF, which
would turn that proxy into exactly the kind of orchestrating reverse
proxy the review's own §4 rejected.

Never a new store, never persisted data of its own - every field below is
read straight from the existing nine Ledger stores via their already-
existing .get()/.all() methods and serialized via atlas.research.
serialization's own existing *_to_dict() functions, unchanged. Read-only:
no method here ever calls .register()/.record() on any store.

Entry points (exactly one required):
- promotion_id: start from a recorded human decision.
- validation_id: start from a specific ValidationResult (e.g. opened
  directly from a LeaderboardEntry that has no promotion decision yet).

The walk never trusts PromotionRecord.evidence_snapshot_ref as a
structural key - that field is free text ("e.g. a ValidationResult id or
a LeaderboardSnapshot id", per PromotionRecord's own docstring), pinned
by a human reviewer for their own reference, not a foreign key this
endpoint can rely on mechanically. Instead: a PromotionRecord's own typed
(hypothesis_id, realization_id) pair is matched structurally against
every recorded LeaderboardEntry - the same match list_promotion_
candidates() itself already performs - to discover which
ValidationResult(s) actually apply. A missing referenced record (a real,
if unexpected, Ledger integrity gap) is reported via `warnings`, never a
500 - this is an operator-facing read tool, not a strict-mode API.

Sprint 10 Slice A.1 (hardening): each of the six Ledger stores this walk
touches (promotions, leaderboard_snapshots, validation_results, evidence,
experiments, realizations) is read via .all() exactly ONCE per request,
up front, into a local id->entity map - every subsequent "lookup" below is
an in-memory dict access, never a second call into a store. This
corrects the original Slice A implementation, which called .get() once
per referenced id (once per evidence_id, once per experiment_id, and so
on) - and since every store's .get()/.all() independently re-reads and
re-parses its entire JSONL file from scratch (atlas/research/stores.py
has no caching or indexing), that meant a single lineage request could
issue 8-9 full file scans instead of the 6 a single .all() pass per store
requires. External behavior (response shape, status codes, warning text)
is unchanged - this is an internal performance correction only.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from atlas.api.deps import get_ledger_readiness, get_ledger_stores
from atlas.research.models import (
    Evidence,
    Experiment,
    LeaderboardEntry,
    LeaderboardSnapshot,
    PromotionRecord,
    Realization,
    ValidationResult,
)
from atlas.research.serialization import (
    evidence_to_dict,
    experiment_to_dict,
    leaderboard_entry_to_dict,
    promotion_record_to_dict,
    realization_to_dict,
    validation_result_to_dict,
)
from atlas.research_deploy.startup_check import LedgerReadiness, LedgerStores

router = APIRouter()


def _degraded_response(readiness: LedgerReadiness) -> Optional[JSONResponse]:
    if readiness.status == "ready":
        return None
    return JSONResponse(
        {"ok": False, "error": f"research ledger storage is degraded: {readiness.reason}", "reason": readiness.reason},
        status_code=503,
    )


@dataclass(frozen=True)
class _LineageMaps:
    """Every Ledger store this endpoint ever touches, read via .all()
    exactly once per request and indexed by id - see this module's own
    docstring (Sprint 10 Slice A.1) for why: every subsequent "lookup"
    anywhere below is a plain dict access, never a second file read."""

    promotions_by_id: dict[str, PromotionRecord]
    snapshots: list[LeaderboardSnapshot]
    validation_results_by_id: dict[str, ValidationResult]
    evidence_by_id: dict[str, Evidence]
    experiments_by_id: dict[str, Experiment]
    realizations_by_id: dict[str, Realization]


def _read_lineage_maps(stores: LedgerStores) -> _LineageMaps:
    return _LineageMaps(
        promotions_by_id={p.promotion_id: p for p in stores.promotions.all()},
        snapshots=stores.leaderboard_snapshots.all(),
        validation_results_by_id={v.validation_id: v for v in stores.validation_results.all()},
        evidence_by_id={e.evidence_id: e for e in stores.evidence.all()},
        experiments_by_id={x.experiment_id: x for x in stores.experiments.all()},
        realizations_by_id={r.realization_id: r for r in stores.realizations.all()},
    )


def _matching_entries(
    maps: _LineageMaps, predicate: Callable[[LeaderboardEntry], bool],
) -> list[tuple[LeaderboardSnapshot, LeaderboardEntry]]:
    """Every (snapshot, entry) pair, across every recorded snapshot, whose
    entry satisfies `predicate` - the one traversal both entry points share,
    parameterized by what they match on: structural (hypothesis_id,
    realization_id) for the promotion_id entry point (the same match
    atlas.research.promotion.service.list_promotion_candidates() already
    performs, never evidence_snapshot_ref), or a direct validation_id match
    for the other (unambiguous by construction once validation_id is
    already known)."""
    return [
        (snapshot, entry)
        for snapshot in maps.snapshots
        for entry in snapshot.entries
        if predicate(entry)
    ]


def _leaderboard_entry_dict(snapshot: LeaderboardSnapshot, entry: LeaderboardEntry) -> dict:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_created_at": snapshot.created_at,
        **leaderboard_entry_to_dict(entry),
    }


def _walk_from_validation_ids(
    validation_ids: set[str], maps: _LineageMaps, warnings: list[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Given a set of already-discovered validation_ids, follows each
    ValidationResult through Evidence to Experiment - deduplicating
    Evidence/Experiment across multiple ValidationResults (in/out-of-sample
    Evidence usually points at two distinct Experiments, and two
    ValidationResults could in principle reference the same Evidence).
    Returns (validation_results, evidence, experiments), each a list of
    already-serialized dicts. Every lookup here is a dict access against
    `maps` - no store is read again."""
    validation_dicts = []
    evidence_by_id: dict[str, dict] = {}
    experiment_by_id: dict[str, dict] = {}

    for validation_id in sorted(validation_ids):
        result = maps.validation_results_by_id.get(validation_id)
        if result is None:
            warnings.append(f"validation result {validation_id!r} referenced by a leaderboard entry but not found in the Ledger")
            continue
        validation_dicts.append(validation_result_to_dict(result))

        for evidence_id in result.evidence_ids:
            if evidence_id in evidence_by_id:
                continue
            evidence = maps.evidence_by_id.get(evidence_id)
            if evidence is None:
                warnings.append(f"evidence {evidence_id!r} referenced by validation result {validation_id!r} but not found in the Ledger")
                continue
            evidence_by_id[evidence_id] = evidence_to_dict(evidence)

            if evidence.experiment_id in experiment_by_id:
                continue
            experiment = maps.experiments_by_id.get(evidence.experiment_id)
            if experiment is None:
                warnings.append(f"experiment {evidence.experiment_id!r} referenced by evidence {evidence_id!r} but not found in the Ledger")
                continue
            experiment_by_id[evidence.experiment_id] = experiment_to_dict(experiment)

    return validation_dicts, list(evidence_by_id.values()), list(experiment_by_id.values())


@router.get("/research/lineage")
async def read_lineage(
    promotion_id: Optional[str] = None,
    validation_id: Optional[str] = None,
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

    if (promotion_id is None) == (validation_id is None):
        return JSONResponse(
            {"ok": False, "error": "exactly one of promotion_id or validation_id is required"},
            status_code=422,
        )

    maps = _read_lineage_maps(ledger_stores)
    warnings: list[str] = []

    if promotion_id is not None:
        requested_promotion = maps.promotions_by_id.get(promotion_id)
        if requested_promotion is None:
            return JSONResponse({"ok": False, "error": f"no promotion record with id {promotion_id!r}"}, status_code=404)
        hypothesis_id = requested_promotion.hypothesis_id
        realization_id = requested_promotion.realization_id
        matches = _matching_entries(
            maps, lambda entry: entry.hypothesis_id == hypothesis_id and entry.realization_id == realization_id,
        )
        if not matches:
            warnings.append(
                f"no leaderboard entry found for (hypothesis_id={hypothesis_id!r}, realization_id={realization_id!r}) - "
                "this promotion decision may have been recorded without a corresponding leaderboard snapshot"
            )
    else:
        requested_validation = maps.validation_results_by_id.get(validation_id)
        if requested_validation is None:
            return JSONResponse({"ok": False, "error": f"no validation result with id {validation_id!r}"}, status_code=404)
        hypothesis_id = requested_validation.hypothesis_id
        realization_id = requested_validation.realization_id
        matches = _matching_entries(maps, lambda entry: entry.validation_id == validation_id)
        if not matches:
            warnings.append(f"validation result {validation_id!r} was not found in any recorded leaderboard snapshot")

    leaderboard_entries = [_leaderboard_entry_dict(snapshot, entry) for snapshot, entry in matches]
    found_validation_ids = {entry.validation_id for _, entry in matches if entry.validation_id is not None}
    if validation_id is not None:
        found_validation_ids.add(validation_id)

    validation_results, evidence, experiments = _walk_from_validation_ids(found_validation_ids, maps, warnings)

    realization = None
    if realization_id is not None:
        found_realization = maps.realizations_by_id.get(realization_id)
        if found_realization is None:
            warnings.append(f"realization {realization_id!r} referenced but not found in the Ledger")
        else:
            realization = realization_to_dict(found_realization)

    promotion_records = [
        promotion_record_to_dict(p)
        for p in maps.promotions_by_id.values()
        if p.hypothesis_id == hypothesis_id and p.realization_id == realization_id
    ]

    return JSONResponse({
        "ok": True,
        "hypothesis_id": hypothesis_id,
        "realization_id": realization_id,
        "requested_promotion_id": promotion_id,
        "requested_validation_id": validation_id,
        "promotion_records": promotion_records,
        "leaderboard_entries": leaderboard_entries,
        "validation_results": validation_results,
        "evidence": evidence,
        "experiments": experiments,
        "realization": realization,
        "warnings": warnings,
    })

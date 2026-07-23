"""
Phase N4 Sprint 7. rank()/snapshot_leaderboard() - see this package's own
__init__.py for the full boundary and why no scientific score is
computed.
"""
from typing import Optional

from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import LeaderboardEntry, LeaderboardSnapshot, ValidationResult, ValidationVerdict
from atlas.research.ports import LeaderboardSnapshotStore
from atlas.research.ranking.models import RankingPolicy

_SCORE_DESCRIPTION = (
    "SUPPORTED; Sprint 7 performs organizational ranking only (by recency of validation) - "
    "no independent scientific quality score is computed. score=1.0 is a compatibility "
    "placeholder required by the frozen LeaderboardEntry.score field and carries no "
    "scientific meaning - see atlas.research.ranking's own docs for why."
)


def _select_latest_per_hypothesis(
    validation_results: list[ValidationResult],
) -> dict[str, ValidationResult]:
    """A hypothesis may contribute at most one entry per snapshot - the
    one with the latest validated_at (ISO-8601 string comparison), ties
    broken by the lexicographically greatest validation_id. Deterministic
    and content-derived; never depends on input order."""
    best: dict[str, ValidationResult] = {}
    for result in validation_results:
        current = best.get(result.hypothesis_id)
        if current is None:
            best[result.hypothesis_id] = result
            continue
        challenger_key = (result.validated_at, result.validation_id)
        current_key = (current.validated_at, current.validation_id)
        if challenger_key > current_key:
            best[result.hypothesis_id] = result
    return best


def rank(validation_results: tuple[ValidationResult, ...], policy: RankingPolicy) -> tuple[LeaderboardEntry, ...]:
    """Pure - no Ledger access. Eligibility: verdict == SUPPORTED only.
    De-duplication: at most one entry per hypothesis_id (see
    _select_latest_per_hypothesis). Ordering: validated_at descending
    (most recently validated first), hypothesis_id ascending as the
    deterministic tie-break - a total order, achieved via two stable
    sorts (first by the ascending tie-break key, then by the descending
    primary key; Python's sort is guaranteed stable, so ties from the
    first pass survive the second in ascending hypothesis_id order).
    `policy` is currently unused beyond being recorded by the caller
    (snapshot_leaderboard()) - v1 has exactly one ordering basis, not yet
    parametrized; accepted as a parameter now so a future, genuinely
    different v2 policy does not require changing this function's own
    signature."""
    del policy  # v1: one fixed ordering basis; accepted for a stable future signature only

    eligible = [r for r in validation_results if r.verdict == ValidationVerdict.SUPPORTED]
    latest_per_hypothesis = _select_latest_per_hypothesis(eligible)

    by_hypothesis_id_ascending = sorted(latest_per_hypothesis.values(), key=lambda r: r.hypothesis_id)
    ordered = sorted(by_hypothesis_id_ascending, key=lambda r: r.validated_at, reverse=True)

    return tuple(
        LeaderboardEntry(
            hypothesis_id=result.hypothesis_id, realization_id=result.realization_id, rank=position,
            score=1.0, score_description=_SCORE_DESCRIPTION, validation_id=result.validation_id,
        )
        for position, result in enumerate(ordered, start=1)
    )


def _compute_snapshot_fingerprint(
    policy: RankingPolicy, entries: tuple[LeaderboardEntry, ...],
    excluded_validation_ids: tuple[str, ...], benchmark_description: Optional[str],
) -> str:
    return compute_fingerprint({
        "ranking_policy_id": policy.policy_id,
        "ranking_policy_version": policy.policy_version,
        "ordered_entries": [
            {
                "hypothesis_id": e.hypothesis_id, "realization_id": e.realization_id,
                "rank": e.rank, "score": e.score, "validation_id": e.validation_id,
            }
            for e in entries
        ],
        "excluded_validation_ids": sorted(excluded_validation_ids),
        "benchmark_description": benchmark_description,
    })


def snapshot_leaderboard(
    validation_results: tuple[ValidationResult, ...],
    policy: RankingPolicy,
    snapshot_id: str,
    created_at: str,
    tracker: LeaderboardSnapshotStore,
    benchmark_description: Optional[str] = None,
) -> LeaderboardSnapshot:
    """The one function in this package that touches the Ledger - via the
    Sprint 2 LeaderboardSnapshotStore Protocol, never a new persistence
    abstraction. excluded_validation_ids records every validation_id from
    the input that did not receive a rank - whether because its own
    verdict was not SUPPORTED, or because it was a hypothesis's own older
    ValidationResult superseded by a more recently validated one -
    preserved for auditability, never silently dropped."""
    entries = rank(validation_results, policy)
    ranked_validation_ids = {e.validation_id for e in entries}
    excluded_validation_ids = tuple(sorted(
        r.validation_id for r in validation_results if r.validation_id not in ranked_validation_ids
    ))
    fingerprint = _compute_snapshot_fingerprint(policy, entries, excluded_validation_ids, benchmark_description)

    snapshot = LeaderboardSnapshot(
        snapshot_id=snapshot_id, created_at=created_at, entries=entries, fingerprint=fingerprint,
        benchmark_description=benchmark_description,
        ranking_policy_id=policy.policy_id, ranking_policy_version=policy.policy_version,
        excluded_validation_ids=excluded_validation_ids,
    )
    tracker.record(snapshot)
    return snapshot

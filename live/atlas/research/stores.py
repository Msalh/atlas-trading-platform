"""
Sprint 28. File-backed, append-only persistence for Hypothesis and
Experiment records - JSON Lines, one record per line, never edited or
deleted in place.

Deliberately NOT a new Postgres table. Sprint 27's own critical review was
explicit that a professional review would flag a full database schema for a
handful of hypotheses as premature machinery ("what's over-engineered, if
built now") - this reuses the exact append-only-log shape
atlas.market_engine's own event store already established (never mutate a
stored row; a status change is a new fact, not an edit) at the smallest
scale that's actually justified today. The trigger for promoting this to a
real database table is a real, named one: when the file grows large enough,
or is accessed concurrently enough, that a linear file scan stops being
adequate - not before.

"Current state" for a record with multiple lines sharing the same ID is the
LATEST line for that ID, by file position - the same "no separate mutable
row, derive current state from the append-only log" principle, applied here
deliberately rather than only observed as a pattern elsewhere. Sprint 28
itself never re-appends a Hypothesis after registering it (no promotion
pipeline exists yet to trigger a status change) - this module supports that
future need without building the promotion logic that would use it now.

Both stores raise if the SAME id is registered/recorded twice with
DIFFERENT content - the same idempotent-or-reject discipline
MarketStateRepository.ingest() already established for its own UNIQUE
constraint (identical resubmission is safe and a no-op; a genuine collision
with different content is a data-integrity error, not something to
silently overwrite).

--- Phase N4 Sprint 2 (Ledger) ---

Adds the seven remaining Sprint 1 entities' stores (FeatureRegistry,
FindingTracker, RealizationRegistry, EvidenceTracker,
ValidationResultTracker, LeaderboardSnapshotTracker,
PromotionRecordTracker), following HypothesisRegistry/ExperimentTracker's
exact shape and reusing their same module-level _read_all_lines/
_append_line/RecordConflictError unchanged - HypothesisRegistry and
ExperimentTracker themselves are not modified.

Verb choice per class follows the same distinction Sprint 28 already
established (register() for an authored proposal that starts a lifecycle;
record() for a computed/completed fact) rather than one flattened verb -
mirroring exactly which entities carry a `provenance` field in models.py
(Feature, Realization: authored, so register(); Finding, Evidence,
ValidationResult, LeaderboardSnapshot, PromotionRecord: computed/decided
facts, so record()).

find_similar_hypotheses() is this sprint's other deliverable: a first,
deliberately minimal similarity check over structural anchor fields
(feature_refs, context_description, outcome_metric) - never `statement`,
which is free text. A textual/exact-match check here would fail Research
Engine Design Principles II.4 outright (see the roadmap's own Sprint 2 risk
note). This is a pure function, not a method on HypothesisRegistry - it
operates on any iterable of already-loaded Hypothesis records, matching
this project's standing preference for computation decoupled from I/O
(the same shape atlas.research.service.run_experiment already takes).
"""
import json
from pathlib import Path
from typing import Iterable, Optional

from atlas.research.models import (
    Evidence,
    Experiment,
    Feature,
    Finding,
    Hypothesis,
    LeaderboardSnapshot,
    PromotionRecord,
    Realization,
    ValidationResult,
)
from atlas.research.serialization import (
    evidence_from_dict,
    evidence_to_dict,
    experiment_from_dict,
    experiment_to_dict,
    feature_from_dict,
    feature_to_dict,
    finding_from_dict,
    finding_to_dict,
    hypothesis_from_dict,
    hypothesis_to_dict,
    leaderboard_snapshot_from_dict,
    leaderboard_snapshot_to_dict,
    promotion_record_from_dict,
    promotion_record_to_dict,
    realization_from_dict,
    realization_to_dict,
    validation_result_from_dict,
    validation_result_to_dict,
)


class RecordConflictError(Exception):
    """Raised when the same id is registered/recorded twice with different
    content - a data-integrity error, never silently resolved either way."""


def _read_all_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _append_line(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")


class HypothesisRegistry:
    """One JSONL file per registry instance - callers point separate
    research efforts at separate files the same way separate
    ProfilingRunConfig calls point at separate symbol/date ranges; this
    module has no opinion on where the file should live."""

    def __init__(self, path: Path):
        self._path = path

    def register(self, hypothesis: Hypothesis) -> None:
        existing = self.get(hypothesis.hypothesis_id)
        new_data = hypothesis_to_dict(hypothesis)
        if existing is not None:
            if hypothesis_to_dict(existing) == new_data:
                return  # identical resubmission - safe no-op
            raise RecordConflictError(
                f"hypothesis {hypothesis.hypothesis_id!r} already registered with different content - "
                f"a hypothesis's content must never change once registered; use a new id for a revised hypothesis"
            )
        _append_line(self._path, new_data)

    def get(self, hypothesis_id: str) -> Optional[Hypothesis]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["hypothesis_id"] == hypothesis_id:
                latest = record
        return None if latest is None else hypothesis_from_dict(latest)

    def all(self) -> list[Hypothesis]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["hypothesis_id"]] = record
        return [hypothesis_from_dict(record) for record in by_id.values()]


class ExperimentTracker:
    """Same append-only, id-conflict-rejecting shape as HypothesisRegistry -
    unlike Hypothesis, an Experiment is never expected to be re-appended
    under the same id at all (an experiment is a completed, immutable
    historical fact the moment it finishes running); the conflict check
    here is defense-in-depth against an experiment_id collision, not a
    supported "update" path."""

    def __init__(self, path: Path):
        self._path = path

    def record(self, experiment: Experiment) -> None:
        existing = self.get(experiment.experiment_id)
        new_data = experiment_to_dict(experiment)
        if existing is not None:
            if experiment_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"experiment {experiment.experiment_id!r} already recorded with different content - "
                f"experiment ids must be unique per run"
            )
        _append_line(self._path, new_data)

    def get(self, experiment_id: str) -> Optional[Experiment]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["experiment_id"] == experiment_id:
                latest = record
        return None if latest is None else experiment_from_dict(latest)

    def all(self) -> list[Experiment]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["experiment_id"]] = record
        return [experiment_from_dict(record) for record in by_id.values()]

    def for_hypothesis(self, hypothesis_id: str) -> list[Experiment]:
        return [e for e in self.all() if e.hypothesis_id == hypothesis_id]


class FeatureRegistry:
    """Same shape as HypothesisRegistry - Feature is an authored proposal
    (it carries `provenance`), so register(), not record()."""

    def __init__(self, path: Path):
        self._path = path

    def register(self, feature: Feature) -> None:
        existing = self.get(feature.feature_id)
        new_data = feature_to_dict(feature)
        if existing is not None:
            if feature_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"feature {feature.feature_id!r} already registered with different content - "
                f"a feature's content must never change once registered; use a new id for a revised feature"
            )
        _append_line(self._path, new_data)

    def get(self, feature_id: str) -> Optional[Feature]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["feature_id"] == feature_id:
                latest = record
        return None if latest is None else feature_from_dict(latest)

    def all(self) -> list[Feature]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["feature_id"]] = record
        return [feature_from_dict(record) for record in by_id.values()]


class FindingTracker:
    """Same shape as ExperimentTracker - Finding is Discovery Engine's
    computed output (no `provenance` field), so record(), not register()."""

    def __init__(self, path: Path):
        self._path = path

    def record(self, finding: Finding) -> None:
        existing = self.get(finding.finding_id)
        new_data = finding_to_dict(finding)
        if existing is not None:
            if finding_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"finding {finding.finding_id!r} already recorded with different content - "
                f"finding ids must be unique per run"
            )
        _append_line(self._path, new_data)

    def get(self, finding_id: str) -> Optional[Finding]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["finding_id"] == finding_id:
                latest = record
        return None if latest is None else finding_from_dict(latest)

    def all(self) -> list[Finding]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["finding_id"]] = record
        return [finding_from_dict(record) for record in by_id.values()]


class RealizationRegistry:
    """Same shape as HypothesisRegistry - Realization is an authored spec
    (it carries `provenance`), so register(), not record()."""

    def __init__(self, path: Path):
        self._path = path

    def register(self, realization: Realization) -> None:
        existing = self.get(realization.realization_id)
        new_data = realization_to_dict(realization)
        if existing is not None:
            if realization_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"realization {realization.realization_id!r} already registered with different content - "
                f"a realization's content must never change once registered; use a new id for a revised realization"
            )
        _append_line(self._path, new_data)

    def get(self, realization_id: str) -> Optional[Realization]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["realization_id"] == realization_id:
                latest = record
        return None if latest is None else realization_from_dict(latest)

    def all(self) -> list[Realization]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["realization_id"]] = record
        return [realization_from_dict(record) for record in by_id.values()]


class EvidenceTracker:
    """Same shape as ExperimentTracker - Evidence is always system-computed
    (Research Engine Design Principles III.1: evidence is computed, not
    judged; no `provenance` field), so record(), not register()."""

    def __init__(self, path: Path):
        self._path = path

    def record(self, evidence: Evidence) -> None:
        existing = self.get(evidence.evidence_id)
        new_data = evidence_to_dict(evidence)
        if existing is not None:
            if evidence_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"evidence {evidence.evidence_id!r} already recorded with different content - "
                f"evidence ids must be unique per run"
            )
        _append_line(self._path, new_data)

    def get(self, evidence_id: str) -> Optional[Evidence]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["evidence_id"] == evidence_id:
                latest = record
        return None if latest is None else evidence_from_dict(latest)

    def all(self) -> list[Evidence]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["evidence_id"]] = record
        return [evidence_from_dict(record) for record in by_id.values()]


class ValidationResultTracker:
    """Same shape as ExperimentTracker - ValidationResult is always
    system-computed (the judgment layer, but never authored; no
    `provenance` field), so record(), not register()."""

    def __init__(self, path: Path):
        self._path = path

    def record(self, result: ValidationResult) -> None:
        existing = self.get(result.validation_id)
        new_data = validation_result_to_dict(result)
        if existing is not None:
            if validation_result_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"validation result {result.validation_id!r} already recorded with different content - "
                f"validation ids must be unique per run"
            )
        _append_line(self._path, new_data)

    def get(self, validation_id: str) -> Optional[ValidationResult]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["validation_id"] == validation_id:
                latest = record
        return None if latest is None else validation_result_from_dict(latest)

    def all(self) -> list[ValidationResult]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["validation_id"]] = record
        return [validation_result_from_dict(record) for record in by_id.values()]


class LeaderboardSnapshotTracker:
    """Same shape as ExperimentTracker - a LeaderboardSnapshot is a
    computed ranking pass's permanent record (Principle II.3: past
    snapshots are never overwritten, only superseded by a newer snapshot
    with its own id), so record(), not register()."""

    def __init__(self, path: Path):
        self._path = path

    def record(self, snapshot: LeaderboardSnapshot) -> None:
        existing = self.get(snapshot.snapshot_id)
        new_data = leaderboard_snapshot_to_dict(snapshot)
        if existing is not None:
            if leaderboard_snapshot_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"leaderboard snapshot {snapshot.snapshot_id!r} already recorded with different content - "
                f"snapshot ids must be unique per ranking pass"
            )
        _append_line(self._path, new_data)

    def get(self, snapshot_id: str) -> Optional[LeaderboardSnapshot]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["snapshot_id"] == snapshot_id:
                latest = record
        return None if latest is None else leaderboard_snapshot_from_dict(latest)

    def all(self) -> list[LeaderboardSnapshot]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["snapshot_id"]] = record
        return [leaderboard_snapshot_from_dict(record) for record in by_id.values()]


class PromotionRecordTracker:
    """Same shape as ExperimentTracker - a PromotionRecord is the
    permanent record of a decision that already happened (see this
    package's models.py's own docstring for why there is no PENDING_REVIEW
    state on this type at all), so record(), not register()."""

    def __init__(self, path: Path):
        self._path = path

    def record(self, promotion: PromotionRecord) -> None:
        existing = self.get(promotion.promotion_id)
        new_data = promotion_record_to_dict(promotion)
        if existing is not None:
            if promotion_record_to_dict(existing) == new_data:
                return
            raise RecordConflictError(
                f"promotion record {promotion.promotion_id!r} already recorded with different content - "
                f"promotion ids must be unique per decision"
            )
        _append_line(self._path, new_data)

    def get(self, promotion_id: str) -> Optional[PromotionRecord]:
        latest = None
        for record in _read_all_lines(self._path):
            if record["promotion_id"] == promotion_id:
                latest = record
        return None if latest is None else promotion_record_from_dict(latest)

    def all(self) -> list[PromotionRecord]:
        by_id: dict[str, dict] = {}
        for record in _read_all_lines(self._path):
            by_id[record["promotion_id"]] = record
        return [promotion_record_from_dict(record) for record in by_id.values()]


def find_similar_hypotheses(candidate: Hypothesis, existing: Iterable[Hypothesis]) -> tuple[Hypothesis, ...]:
    """Sprint 2's first, deliberately minimal duplicate-detection check
    (Research Engine Design Principles II.4) - superseded by a fuller
    version once Sprint 11's Memory package exists. Structural, never
    textual: compares feature_refs (as a set, order-independent),
    context_description, and outcome_metric - `statement` (free text) is
    never inspected, per those fields' own documented role in models.py's
    Hypothesis docstring.

    A candidate or existing record with no anchor fields set (empty
    feature_refs, or context_description/outcome_metric still None) is
    never matched against anything - there is nothing structural to
    compare, and treating "no anchors" as a wildcard match would produce
    exactly the false positives Principle II.4 exists to avoid. The
    candidate's own id is always excluded from its own results, in case a
    caller passes a candidate that is already present in `existing`."""
    if not candidate.feature_refs or candidate.context_description is None or candidate.outcome_metric is None:
        return ()
    candidate_features = frozenset(candidate.feature_refs)
    matches = []
    for other in existing:
        if other.hypothesis_id == candidate.hypothesis_id:
            continue
        if not other.feature_refs or other.context_description is None or other.outcome_metric is None:
            continue
        if (
            frozenset(other.feature_refs) == candidate_features
            and other.context_description == candidate.context_description
            and other.outcome_metric == candidate.outcome_metric
        ):
            matches.append(other)
    return tuple(matches)

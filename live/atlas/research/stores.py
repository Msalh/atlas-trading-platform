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
"""
import json
from pathlib import Path
from typing import Optional

from atlas.research.models import Experiment, Hypothesis
from atlas.research.serialization import (
    experiment_from_dict,
    experiment_to_dict,
    hypothesis_from_dict,
    hypothesis_to_dict,
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

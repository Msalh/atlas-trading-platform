"""
Production-hardening amendment 3, extended by two follow-on amendments:
cross-snapshot dataset-identity consistency, and a structured
status/reason/detail readiness contract (replacing a single free-text
reason string).

Startup-time validation of the checked-in live/research/snapshots/*.json
files, computed ONCE at process start (atlas.main's lifespan calls
check_snapshots() and stores the result on app.state.snapshots_readiness)
rather than discovered only on the first request that happens to hit a
FROZEN endpoint.

Deliberately does NOT raise or otherwise fail startup on a missing/
invalid snapshot: LIVE endpoints (rule-engine/setup-engine) have zero
dependency on these files and must keep working regardless. FROZEN
endpoints already return a structured 503 on a missing file
(atlas/api/v1/research.py's own SnapshotNotFoundError path, extended
here to also cover schema/checksum/identity failures) - this module's
result is surfaced separately via GET /status, specifically so degraded
state is visible without needing to hit a FROZEN endpoint to discover
it, and never folds into the FROZEN Dataset Health payload itself (which
describes only the research baseline's own certification/warnings/
segment content, never operational/deployment state).

check_snapshots() itself is expected to handle every bad-file case
without raising (that's the whole point of its two-phase validation
below) - but atlas.main's lifespan additionally wraps the call in its
own try/except, falling back to internal_error_readiness() (reason
"internal_error") for the rare case of a genuine bug in this module
raising something unanticipated. This is a second, outer safety net on
top of the same "never block LIVE, never crash startup" contract, not a
relaxation of it.

Two-phase validation:
1. Each of the three files is validated independently first - existence,
   valid JSON, required envelope/schema shape (including
   dataset_identity's own nested fields, needed before phase 2 can safely
   read them), and payload checksum.
2. ONLY once all three pass phase 1 does this module compare
   dataset_identity (symbol, timeframe, row_count, date_range.start,
   date_range.end) across all three. A mismatch marks ALL THREE files
   invalid with reason "dataset_identity_mismatch" - never just the ones
   that disagree with an arbitrarily chosen "reference" file, since there
   is no way to know which of three disagreeing snapshots is the correct
   one. Silently trusting one of them would be exactly the kind of
   unreported inconsistency this check exists to catch.

Every result carries a stable, machine-readable `reason` code (one of
FailureReason's five values, or None when ready) plus a separate,
sanitized, operator-readable `detail` string - never a raw filesystem
path or a raw exception's str() (which can embed one), never a stack
trace.

This module does not replace atlas/api/v1/research.py's own lazy-load-
and-cache path - that remains the sole source of truth for what a live
request to a FROZEN endpoint actually returns. This module only makes
the same checks visible before the first request, not instead of them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from atlas.research_export.serialization import content_checksum

SnapshotStatus = Literal["ready", "missing", "invalid"]

FailureReason = Literal[
    "missing_file", "json_error", "schema_error", "checksum_mismatch", "dataset_identity_mismatch",
    "internal_error",
]

EXPECTED_SNAPSHOT_FILES = ("re1-summary.v1.json", "re2-summary.v1.json", "dataset-health.v1.json")

_REQUIRED_ENVELOPE_KEYS = (
    "schema_version", "source_computation_version", "snapshot_exporter_version",
    "content_checksum", "exported_at", "dataset_identity",
)
_REQUIRED_IDENTITY_KEYS = ("symbol", "timeframe", "row_count", "date_range")
_REQUIRED_DATE_RANGE_KEYS = ("start", "end")

# The fields this module cross-checks (Part 1's "at minimum" list).
# date_range's two sub-fields are compared individually, not as a whole
# object, so a mismatch report can name exactly which one differs.
_IDENTITY_SCALAR_FIELDS = ("symbol", "timeframe", "row_count")
_IDENTITY_DATE_RANGE_FIELDS = ("start", "end")


@dataclass(frozen=True)
class SnapshotCheckResult:
    filename: str
    status: SnapshotStatus
    reason: Optional[FailureReason]  # None only when status == "ready"
    detail: Optional[str]  # sanitized, operator-readable; never a raw path or traceback


@dataclass(frozen=True)
class SnapshotsReadiness:
    results: tuple[SnapshotCheckResult, ...]

    @property
    def all_ready(self) -> bool:
        """Preserved for backward compatibility with existing consumers -
        the structured status/reason fields below are the fuller contract,
        but all_ready's boolean meaning is unchanged."""
        return all(r.status == "ready" for r in self.results)

    @property
    def status(self) -> SnapshotStatus:
        if self.all_ready:
            return "ready"
        if any(r.status == "invalid" for r in self.results):
            return "invalid"
        return "missing"

    @property
    def reason(self) -> Optional[FailureReason]:
        """The first non-None per-file reason, in EXPECTED_SNAPSHOT_FILES
        order - not a severity ranking, just a deterministic pick when
        more than one file is failing for different reasons. A
        dataset_identity_mismatch, by construction, only ever appears
        alongside other files also reporting dataset_identity_mismatch
        (see check_snapshots), so it can never be masked by an unrelated
        single-file failure reported first."""
        for r in self.results:
            if r.reason is not None:
                return r.reason
        return None

    def status_for(self, filename: str) -> SnapshotCheckResult:
        for r in self.results:
            if r.filename == filename:
                return r
        raise KeyError(f"{filename!r} is not one of the expected snapshot files")

    def to_dict(self) -> dict:
        """The shape GET /status exposes - never used by /dataset-health,
        which describes only the frozen research content itself."""
        return {
            "status": self.status,
            "reason": self.reason,
            "all_ready": self.all_ready,
            "files": {
                r.filename: {"status": r.status, "reason": r.reason, "detail": r.detail}
                for r in self.results
            },
        }


def _check_one(directory: Path, filename: str) -> tuple[SnapshotCheckResult, Optional[dict]]:
    """Phase 1 for a single file. Returns (result, loaded_snapshot) - the
    loaded dict is only returned when status == "ready", so phase 2 never
    has to re-validate anything phase 1 already confirmed."""
    path = directory / filename
    if not path.exists():
        return (
            SnapshotCheckResult(filename, "missing", "missing_file",
                                 "snapshot file not found - run scripts/export_research_snapshots.py"),
            None,
        )

    try:
        with open(path, encoding="utf-8") as f:
            snapshot = json.load(f)
    except json.JSONDecodeError as e:
        # JSONDecodeError's own str() never embeds the file path - safe to
        # include msg/lineno directly.
        return (
            SnapshotCheckResult(filename, "invalid", "json_error", f"file is not valid JSON: {e.msg} (line {e.lineno})"),
            None,
        )
    except OSError:
        # OSError's str() commonly DOES embed the absolute path (e.g.
        # FileNotFoundError) - deliberately not included in detail.
        return SnapshotCheckResult(filename, "invalid", "json_error", "file could not be read"), None

    if not isinstance(snapshot, dict) or "envelope" not in snapshot or "payload" not in snapshot:
        return (
            SnapshotCheckResult(filename, "invalid", "schema_error", "missing top-level 'envelope' or 'payload' key"),
            None,
        )

    envelope = snapshot["envelope"]
    if not isinstance(envelope, dict):
        return SnapshotCheckResult(filename, "invalid", "schema_error", "'envelope' is not an object"), None

    missing_keys = [k for k in _REQUIRED_ENVELOPE_KEYS if k not in envelope]
    if missing_keys:
        return (
            SnapshotCheckResult(filename, "invalid", "schema_error", f"envelope missing required keys: {missing_keys}"),
            None,
        )

    identity = envelope["dataset_identity"]
    if not isinstance(identity, dict) or any(k not in identity for k in _REQUIRED_IDENTITY_KEYS):
        return (
            SnapshotCheckResult(filename, "invalid", "schema_error", "dataset_identity is missing required fields"),
            None,
        )
    date_range = identity["date_range"]
    if not isinstance(date_range, dict) or any(k not in date_range for k in _REQUIRED_DATE_RANGE_KEYS):
        return (
            SnapshotCheckResult(filename, "invalid", "schema_error", "dataset_identity.date_range is missing start/end"),
            None,
        )

    recomputed = content_checksum(snapshot["payload"])
    if recomputed != envelope["content_checksum"]:
        return (
            SnapshotCheckResult(
                filename, "invalid", "checksum_mismatch",
                f"content checksum mismatch: envelope claims {envelope['content_checksum'][:16]}..., "
                f"recomputed {recomputed[:16]}... from the payload actually on disk",
            ),
            None,
        )

    return SnapshotCheckResult(filename, "ready", None, None), snapshot


def _identity_mismatch_detail(identities: dict[str, dict]) -> Optional[str]:
    """None when every file's dataset_identity agrees on all compared
    fields; otherwise a sanitized (no paths, no payload content) summary
    naming exactly which fields differ."""
    filenames = list(identities.keys())
    reference = filenames[0]
    differing_fields = []

    for field in _IDENTITY_SCALAR_FIELDS:
        values = {f: identities[f].get(field) for f in filenames}
        if len(set(values.values())) > 1:
            differing_fields.append(field)

    for field in _IDENTITY_DATE_RANGE_FIELDS:
        values = {f: identities[f].get("date_range", {}).get(field) for f in filenames}
        if len(set(values.values())) > 1:
            differing_fields.append(f"date_range.{field}")

    if not differing_fields:
        return None
    return (
        f"dataset_identity disagrees across snapshots in: {', '.join(differing_fields)} "
        f"(reference file: {reference})"
    )


def internal_error_readiness() -> SnapshotsReadiness:
    """Fallback used by atlas.main's startup lifespan when check_snapshots()
    itself raises an exception this module did not anticipate (a bug in
    this check, not a bad snapshot file - check_snapshots() already turns
    every bad-file case it knows about into a normal "invalid" result
    rather than raising). Per this module's own contract above, that must
    never be allowed to fail application startup or take LIVE endpoints
    down with it - so every expected file is marked invalid with the same
    stable "internal_error" reason, meaning SnapshotsReadiness.status_for()
    still resolves for all three filenames exactly as it would after a
    normal check_snapshots() run. FROZEN endpoints keep returning their
    existing structured 503 (via research.py's _degraded_response) instead
    of a KeyError from status_for(), and GET /status keeps reporting a
    well-formed degraded state instead of the request itself failing."""
    return SnapshotsReadiness(tuple(
        SnapshotCheckResult(
            filename, "invalid", "internal_error",
            "snapshot readiness check failed unexpectedly at startup - see server logs",
        )
        for filename in EXPECTED_SNAPSHOT_FILES
    ))


def check_snapshots(directory: Path) -> SnapshotsReadiness:
    """Pure aside from file I/O - safe to call at startup, and directly
    testable against a tmp_path fixture without touching the real
    checked-in files."""
    results: list[SnapshotCheckResult] = []
    identities: dict[str, dict] = {}

    for filename in EXPECTED_SNAPSHOT_FILES:
        result, snapshot = _check_one(directory, filename)
        results.append(result)
        if result.status == "ready" and snapshot is not None:
            identities[filename] = snapshot["envelope"]["dataset_identity"]

    # Phase 2: only once every file has independently passed phase 1.
    if len(identities) == len(EXPECTED_SNAPSHOT_FILES):
        mismatch_detail = _identity_mismatch_detail(identities)
        if mismatch_detail is not None:
            # Every file is marked invalid, not just the ones that differ
            # from some arbitrarily chosen "reference" - there is no way
            # to know which snapshot is actually correct, so none of them
            # is silently trusted.
            results = [
                SnapshotCheckResult(r.filename, "invalid", "dataset_identity_mismatch", mismatch_detail)
                for r in results
            ]

    return SnapshotsReadiness(tuple(results))

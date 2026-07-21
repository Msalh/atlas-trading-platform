"""
Production-hardening amendment 3. Startup-time validation of the
checked-in live/research/snapshots/*.json files - existence, JSON/
schema-envelope shape, and content checksum - computed ONCE at process
start (atlas.main's lifespan calls check_snapshots() and stores the
result on app.state.snapshots_readiness) rather than discovered only on
the first request that happens to hit a FROZEN endpoint.

Deliberately does NOT raise or otherwise fail startup on a missing/
invalid snapshot: LIVE endpoints (rule-engine/setup-engine) have zero
dependency on these files and must keep working regardless. FROZEN
endpoints already return a structured 503 on a missing file
(atlas/api/v1/research.py's own SnapshotNotFoundError path, extended
here to also cover schema/checksum failures) - this module's result is
surfaced separately via GET /status, specifically so degraded state is
visible without needing to hit a FROZEN endpoint to discover it, and
never folds into the FROZEN Dataset Health payload itself (which
describes only the research baseline's own certification/warnings/
segment content, never operational/deployment state).

This module does not replace atlas/api/v1/research.py's own lazy-load-
and-cache path - that remains the sole source of truth for what a live
request to a FROZEN endpoint actually returns. This module only makes
the same three checks visible before the first request, not instead of
them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from atlas.research_export.serialization import content_checksum

SnapshotStatus = Literal["ready", "missing", "invalid"]

EXPECTED_SNAPSHOT_FILES = ("re1-summary.v1.json", "re2-summary.v1.json", "dataset-health.v1.json")

_REQUIRED_ENVELOPE_KEYS = (
    "schema_version", "source_computation_version", "snapshot_exporter_version",
    "content_checksum", "exported_at", "dataset_identity",
)


@dataclass(frozen=True)
class SnapshotCheckResult:
    filename: str
    status: SnapshotStatus
    reason: Optional[str]  # always None when status == "ready"


@dataclass(frozen=True)
class SnapshotsReadiness:
    results: tuple[SnapshotCheckResult, ...]

    @property
    def all_ready(self) -> bool:
        return all(r.status == "ready" for r in self.results)

    def status_for(self, filename: str) -> SnapshotCheckResult:
        for r in self.results:
            if r.filename == filename:
                return r
        raise KeyError(f"{filename!r} is not one of the expected snapshot files")

    def to_dict(self) -> dict:
        """The shape GET /status exposes - never used by /dataset-health,
        which describes only the frozen research content itself."""
        return {
            "all_ready": self.all_ready,
            "files": {r.filename: {"status": r.status, "reason": r.reason} for r in self.results},
        }


def _check_one(directory: Path, filename: str) -> SnapshotCheckResult:
    path = directory / filename
    if not path.exists():
        return SnapshotCheckResult(filename, "missing", f"{path} does not exist")

    try:
        with open(path, encoding="utf-8") as f:
            snapshot = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return SnapshotCheckResult(filename, "invalid", f"could not read/parse file: {e}")

    if not isinstance(snapshot, dict) or "envelope" not in snapshot or "payload" not in snapshot:
        return SnapshotCheckResult(filename, "invalid", "missing top-level 'envelope' or 'payload' key")

    envelope = snapshot["envelope"]
    if not isinstance(envelope, dict):
        return SnapshotCheckResult(filename, "invalid", "'envelope' is not an object")

    missing_keys = [k for k in _REQUIRED_ENVELOPE_KEYS if k not in envelope]
    if missing_keys:
        return SnapshotCheckResult(filename, "invalid", f"envelope missing required keys: {missing_keys}")

    recomputed = content_checksum(snapshot["payload"])
    if recomputed != envelope["content_checksum"]:
        return SnapshotCheckResult(
            filename, "invalid",
            f"content checksum mismatch: envelope claims {envelope['content_checksum'][:16]}..., "
            f"recomputed {recomputed[:16]}... from the payload actually on disk",
        )

    return SnapshotCheckResult(filename, "ready", None)


def check_snapshots(directory: Path) -> SnapshotsReadiness:
    """Pure aside from file I/O - safe to call at startup, and directly
    testable against a tmp_path fixture without touching the real
    checked-in files."""
    return SnapshotsReadiness(tuple(_check_one(directory, f) for f in EXPECTED_SNAPSHOT_FILES))

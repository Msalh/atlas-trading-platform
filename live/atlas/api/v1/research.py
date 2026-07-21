"""
UI v2. GET /api/v1/research/re1/summary, /re2/summary, /dataset-health -
read-only reads of the checked-in live/research/snapshots/*.json files
produced by scripts/export_research_snapshots.py. No computation happens
on request, and no markdown parsing - architecture doc §5/§6.

Production-hardening amendment 2: snapshots live inside live/, not at the
repo root, specifically so the path below - resolved relative to this
module's own location, never to os.getcwd() or a repo-root-relative
climb - keeps working regardless of which directory a deployment
platform happens to select as its build/run root. Do not move this
directory back to the repo root; a Railway (or similar) build that only
includes the `live/` subtree would silently ship without these files.

Snapshots are loaded lazily and cached in-process (module-level dict) on
first request per file - the files only change when a human explicitly
re-runs the export script and redeploys, never at runtime, so a
process-lifetime cache is correct, not just an optimization. Startup
validation (atlas/research_export/startup_check.py, wired into
atlas.main's lifespan) additionally checks existence/schema/checksum
once at process start and exposes a ready/missing/invalid status via
GET /status - this module's own lazy-load/503 behavior is unchanged and
still the source of truth for what a live request actually gets.

Protected by the same shared API_KEY every other read endpoint in this
app uses (Depends(require_api_key), applied at router-registration time
in atlas/main.py) - same posture as rule_engine.py's own router.
"""
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from atlas.api.deps import get_snapshots_readiness
from atlas.research_export.startup_check import SnapshotsReadiness

router = APIRouter()

# live/atlas/api/v1/research.py -> parents[3] is live/ - independent of cwd
# and of whether a deployment's build root is live/ or the repo root.
# Public (not underscore-prefixed) since atlas/research_export/startup_check.py
# also needs this exact path.
SNAPSHOTS_DIR = Path(__file__).resolve().parents[3] / "research" / "snapshots"
_SCHEMA_VERSION = "1.0"

_cache: dict[str, dict] = {}


class SnapshotNotFoundError(Exception):
    pass


def _load_snapshot(filename: str) -> dict:
    if filename in _cache:
        return _cache[filename]
    path = SNAPSHOTS_DIR / filename
    if not path.exists():
        raise SnapshotNotFoundError(f"{filename} does not exist at {path} - run scripts/export_research_snapshots.py")
    with open(path, encoding="utf-8") as f:
        snapshot = json.load(f)
    _cache[filename] = snapshot
    return snapshot


def _http_envelope(snapshot: dict, warnings: Optional[list[str]] = None) -> dict[str, Any]:
    """Wraps a snapshot's on-disk envelope (models.SnapshotEnvelope's own
    shape) into the shared HTTP response envelope every UI v2 endpoint
    uses (architecture doc §6) - source_track is always "frozen" here,
    code_version is source_computation_version (NEVER
    snapshot_exporter_version - amendment 2)."""
    file_envelope = snapshot["envelope"]
    identity = file_envelope["dataset_identity"]
    return {
        "schema_version": _SCHEMA_VERSION,
        "source_track": "frozen",
        "symbol": identity["symbol"],
        "timeframe": identity["timeframe"],
        "generated_at": file_envelope["exported_at"],
        "data_as_of": identity["date_range"]["end"],
        "code_version": file_envelope["source_computation_version"],
        "warnings": warnings or [],
    }


def _degraded_response(filename: str, readiness: SnapshotsReadiness) -> Optional[JSONResponse]:
    """Production-hardening amendment 3: gate on the one-time startup check
    before attempting to load anything, so an "invalid" snapshot (bad
    checksum, malformed schema) 503s with a clear reason exactly like a
    "missing" one always has, rather than being loaded blind and either
    crashing or silently serving corrupt content. Returns None when ready
    (the only case where the caller should proceed to _load_snapshot)."""
    result = readiness.status_for(filename)
    if result.status == "ready":
        return None
    return JSONResponse(
        {"ok": False, "error": f"research snapshot {result.status}: {result.reason}"}, status_code=503,
    )


def _snapshot_response(filename: str, body_key: str, readiness: SnapshotsReadiness) -> JSONResponse:
    degraded = _degraded_response(filename, readiness)
    if degraded is not None:
        return degraded
    try:
        snapshot = _load_snapshot(filename)
    except SnapshotNotFoundError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    envelope = _http_envelope(snapshot)
    return JSONResponse({"ok": True, "envelope": envelope, body_key: snapshot["payload"]}, status_code=200)


@router.get("/research/re1/summary")
async def read_re1_summary(readiness: SnapshotsReadiness = Depends(get_snapshots_readiness)):
    return _snapshot_response("re1-summary.v1.json", "report", readiness)


@router.get("/research/re2/summary")
async def read_re2_summary(readiness: SnapshotsReadiness = Depends(get_snapshots_readiness)):
    return _snapshot_response("re2-summary.v1.json", "report", readiness)


@router.get("/research/dataset-health")
async def read_dataset_health(readiness: SnapshotsReadiness = Depends(get_snapshots_readiness)):
    degraded = _degraded_response("dataset-health.v1.json", readiness)
    if degraded is not None:
        return degraded
    try:
        snapshot = _load_snapshot("dataset-health.v1.json")
    except SnapshotNotFoundError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    envelope = _http_envelope(snapshot, warnings=[
        f"{w['id']}: {w['title']}" for w in snapshot["payload"]["known_warnings"] if w["severity"] == "fail"
    ])
    payload = snapshot["payload"]
    return JSONResponse({
        "ok": True,
        "envelope": envelope,
        "dataset_identity": payload["dataset_identity"],
        "segment_count": payload["segment_count"],
        "certification": payload["certification"],
        "known_warnings": payload["known_warnings"],
        "frozen_version": {
            "source_computation_version": snapshot["envelope"]["source_computation_version"],
            "exported_at": snapshot["envelope"]["exported_at"],
        },
    }, status_code=200)

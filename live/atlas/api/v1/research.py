"""
UI v2. GET /api/v1/research/re1/summary, /re2/summary, /dataset-health -
read-only reads of the checked-in research/snapshots/*.json files
produced by scripts/export_research_snapshots.py. No computation happens
on request, and no markdown parsing - architecture doc §5/§6.

Snapshots are loaded lazily and cached in-process (module-level dict) on
first request per file - the files only change when a human explicitly
re-runs the export script and redeploys, never at runtime, so a
process-lifetime cache is correct, not just an optimization.

Protected by the same shared API_KEY every other read endpoint in this
app uses (Depends(require_api_key), applied at router-registration time
in atlas/main.py) - same posture as rule_engine.py's own router.
"""
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_SNAPSHOTS_DIR = Path(__file__).resolve().parents[4] / "research" / "snapshots"
_SCHEMA_VERSION = "1.0"

_cache: dict[str, dict] = {}


class SnapshotNotFoundError(Exception):
    pass


def _load_snapshot(filename: str) -> dict:
    if filename in _cache:
        return _cache[filename]
    path = _SNAPSHOTS_DIR / filename
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


def _snapshot_response(filename: str, body_key: str) -> JSONResponse:
    try:
        snapshot = _load_snapshot(filename)
    except SnapshotNotFoundError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    envelope = _http_envelope(snapshot)
    return JSONResponse({"ok": True, "envelope": envelope, body_key: snapshot["payload"]}, status_code=200)


@router.get("/research/re1/summary")
async def read_re1_summary():
    return _snapshot_response("re1-summary.v1.json", "report")


@router.get("/research/re2/summary")
async def read_re2_summary():
    return _snapshot_response("re2-summary.v1.json", "report")


@router.get("/research/dataset-health")
async def read_dataset_health():
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

"""Authenticated, sanitized read API for persisted Phase 18 analysis."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

router = APIRouter()


def _record(value: Any) -> dict[str, Any]:
    return {
        "snapshot_id": value.snapshot_id,
        "state": value.outcome,
        "timestamp": value.recorded_at,
        "summary": value.summary,
        "citations": list(value.citations),
        "limitations": list(value.limitations),
        "reason": value.reason,
        "audit": {
            "analysis_audit_id": value.analysis_audit_id,
            "analysis_output_id": value.analysis_output_id,
        },
    }


@router.get("/ai-analysis/latest")
def latest_analysis(request: Request) -> dict[str, Any]:
    runtime = getattr(request.app.state, "ai_persistence_runtime", None)
    store = getattr(runtime, "shadow_store", None)
    if runtime is None or getattr(runtime, "state", None) != "ready" or store is None:
        return {"status": "not_integrated", "latest": None}
    try:
        latest = store.latest()
    except Exception:  # noqa: BLE001 - public read failure is sanitized
        return {"status": "unavailable", "latest": None}
    return {
        "status": "available" if latest is not None else "no_result",
        "latest": _record(latest) if latest is not None else None,
    }


@router.get("/ai-analysis/history")
def analysis_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    runtime = getattr(request.app.state, "ai_persistence_runtime", None)
    store = getattr(runtime, "shadow_store", None)
    if runtime is None or getattr(runtime, "state", None) != "ready" or store is None:
        return {"status": "not_integrated", "history": []}
    try:
        history = store.history(limit=limit)
    except Exception:  # noqa: BLE001 - public read failure is sanitized
        return {"status": "unavailable", "history": []}
    return {
        "status": "available" if history else "no_result",
        "history": [_record(item) for item in history],
    }

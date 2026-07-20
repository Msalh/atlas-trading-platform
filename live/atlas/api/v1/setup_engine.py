"""
UI v2. GET /api/v1/setup-engine/latest, GET /api/v1/setup-engine/episodes/live.
Zero changes to atlas/setup_engine/ or atlas/rule_engine/ anywhere in this
file - every call composes their existing public functions.

`/latest` mirrors atlas/rule_engine/service.py's own
evaluate_latest_rule_engine_output() one layer up: fetch just enough
MarketState history to satisfy both registries' required_history, build
the RuleEngineOutput window, then the SetupEngineOutput window, and return
the last position - the same "minimal trailing history, no episode
construction" shape rule_engine.py's own /latest route already has. This
orchestration lives here rather than inside atlas/setup_engine/service.py
specifically so that package is never touched by this work at all - not
because adding it there would have been wrong in principle (the existing
evaluate_latest_rule_engine_output is exactly this kind of function, one
layer down), just the more conservative reading of "no changes to Setup
Engine computation".

`/episodes/live` wires atlas.live_view.episode_projector
.build_live_window_result() - the one place in this design with real
composition logic, documented in that module itself - through the
bar-and-registry-fingerprint-keyed cache (atlas.live_view.cache), with
in-flight request coalescing (one computation per cache key even under
concurrent requests) via a per-key asyncio.Lock.
"""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from atlas.api.deps import get_market_state_repository
from atlas.api.v1.rule_engine import _parse_symbol_and_timeframe
from atlas.core.primitives import Symbol, Timeframe
from atlas.live_view import episode_projector
from atlas.live_view.cache import LiveWindowCache, build_cache_key
from atlas.live_view.models import LiveEpisodeProjection, LiveSetupSnapshot, LiveWindowResult
from atlas.market_engine.ports import MarketStateRepository
from atlas.research.service import current_code_version
from atlas.rule_engine.registry import REGISTRY as RULE_ENGINE_REGISTRY
from atlas.rule_engine.registry import required_history as rule_engine_required_history
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.registry import REGISTRY as SETUP_REGISTRY
from atlas.setup_engine.registry import required_history as setup_engine_required_history
from atlas.setup_engine.service import build_setup_engine_output_window, setup_engine_output_to_dict

router = APIRouter()

_SCHEMA_VERSION = "1.0"
_cache = LiveWindowCache()
_in_flight_locks: dict[tuple, asyncio.Lock] = {}


async def evaluate_latest_setup_engine_output(
    symbol: Symbol, timeframe: Timeframe, repository: MarketStateRepository,
):
    """Returns the latest SetupEngineOutput, or None if nothing has been
    ingested yet - same posture as evaluate_latest_rule_engine_output."""
    total_needed = rule_engine_required_history(RULE_ENGINE_REGISTRY) + setup_engine_required_history(SETUP_REGISTRY) - 1
    history = await repository.get_history(symbol, timeframe, limit=max(total_needed, 1))
    if not history:
        return None
    market_state_window = list(reversed(history))
    rule_outputs = build_rule_engine_output_window(market_state_window)
    setup_outputs = build_setup_engine_output_window(rule_outputs, SETUP_REGISTRY)
    return setup_outputs[-1]


def _live_envelope(symbol: str, timeframe: str, data_as_of: str, warnings: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "source_track": "live",
        "symbol": symbol,
        "timeframe": timeframe,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_as_of": data_as_of,
        "code_version": current_code_version(),
        "warnings": warnings or [],
    }


@router.get("/setup-engine/latest")
async def read_latest_setup_engine_output(
    symbol: str, timeframe: str,
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    output = await evaluate_latest_setup_engine_output(parsed_symbol, parsed_timeframe, repository)
    if output is None:
        return JSONResponse({"ok": True, "found": False, "data": None}, status_code=200)

    envelope = _live_envelope(symbol, timeframe, output.occurred_at)
    return JSONResponse(
        {"ok": True, "found": True, "envelope": envelope, "data": setup_engine_output_to_dict(output)},
        status_code=200,
    )


def _episode_projection_to_dict(ep: LiveEpisodeProjection) -> dict[str, Any]:
    return {
        "setup_name": ep.setup_name,
        "left_boundary_reason": ep.left_boundary_reason.value,
        "activation_timestamp_observed": ep.activation_timestamp_observed,
        "observed_start_timestamp": ep.observed_start_timestamp,
        "duration_bars_observed": ep.duration_bars_observed,
        "is_window_truncated": ep.is_window_truncated,
        "is_active": ep.is_active,
        "last_observed_timestamp": ep.last_observed_timestamp,
        "end_timestamp_observed": ep.end_timestamp_observed,
        "termination_reason": ep.termination_reason.value if ep.termination_reason else None,
        "right_boundary_observed": ep.right_boundary_observed,
        "is_continuation": ep.is_continuation,
        "start_state": asdict(ep.start_state),
        "end_state": asdict(ep.end_state),
    }


def _setup_snapshot_to_dict(snapshot: LiveSetupSnapshot) -> dict[str, Any]:
    return {
        "current_episode": _episode_projection_to_dict(snapshot.current_episode) if snapshot.current_episode else None,
        "recent_episodes": [_episode_projection_to_dict(ep) for ep in snapshot.recent_episodes],
        "computability": {
            "computable_bars": snapshot.computability.computable_bars,
            "non_computable_bars": snapshot.computability.non_computable_bars,
            "detected_true_bars": snapshot.computability.detected_true_bars,
            "detected_false_bars": snapshot.computability.detected_false_bars,
            "insufficient_reason_counts": dict(snapshot.computability.insufficient_reason_counts),
        },
    }


def _live_window_result_to_dict(result: LiveWindowResult) -> dict[str, Any]:
    return {
        "window": {"requested": result.requested_window, "actually_used": result.actually_used_window},
        "setups": {name: _setup_snapshot_to_dict(snap) for name, snap in result.setups.items()},
        "segments": [
            {"segment_id": s.segment_id, "start_timestamp": s.start_timestamp, "end_timestamp": s.end_timestamp}
            for s in result.segments
        ],
        "activation_events": [
            {"timestamp": e.timestamp, "segment_id": e.segment_id, "activated_setups": list(e.activated_setups)}
            for e in result.activation_events
        ],
    }


async def _get_or_compute(
    symbol: Symbol, timeframe: Timeframe, window: int, hard_max_window: int, repository: MarketStateRepository,
) -> Optional[LiveWindowResult]:
    latest = await repository.get_latest(symbol, timeframe)
    if latest is None:
        return None
    latest_timestamp = latest.envelope.occurred_at.isoformat()
    key = build_cache_key(symbol.ticker, timeframe.value, window, latest_timestamp)

    cached = _cache.get(key)
    if cached is not None:
        return cached

    lock = _in_flight_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache.get(key)  # re-check: another request may have finished while we waited
        if cached is not None:
            return cached
        result = await episode_projector.build_live_window_result(
            repository, symbol, timeframe, window=window, hard_max_window=hard_max_window,
        )
        if result is not None:
            _cache.put(key, result)
        return result


@router.get("/setup-engine/episodes/live")
async def read_live_episodes(
    symbol: str, timeframe: str, window: int = episode_projector.DEFAULT_WINDOW,
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    bounded_window = max(1, min(window, episode_projector.HARD_MAX_WINDOW))
    result = await _get_or_compute(
        parsed_symbol, parsed_timeframe, bounded_window, episode_projector.HARD_MAX_WINDOW, repository,
    )
    if result is None:
        return JSONResponse({"ok": True, "found": False, "data": None}, status_code=200)

    envelope = _live_envelope(symbol, timeframe, result.data_as_of, warnings=list(result.warnings))
    return JSONResponse(
        {"ok": True, "found": True, "envelope": envelope, **_live_window_result_to_dict(result)},
        status_code=200,
    )

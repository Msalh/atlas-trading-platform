"""
POST /webhook (also mounted at /api/v1/webhook - see atlas/main.py). Same external
contract as Sprint 0: three event types keyed by "type", correlated by
"correlation_id", 200/207/208 response codes with the same meaning as before. This
module is orchestration only - the atomicity/idempotency guarantee lives in
TradeRepository.claim_and_forward, and the PickMyTrade HTTP call lives in
atlas.services.pickmytrade.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from atlas.api.deps import get_event_bus, get_repository
from atlas.config import settings
from atlas.events import types as event_types
from atlas.events.bus import EventBus
from atlas.repositories.base import TradeRepository
from atlas.services.claude import analyze_with_claude
from atlas.services.pickmytrade import forward_to_pickmytrade

logger = logging.getLogger("atlas.webhook")

router = APIRouter()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def run_claude_analysis(
    payload: dict, correlation_id: str, repository: TradeRepository, event_bus: EventBus,
) -> None:
    """Background task - runs after the HTTP response is already sent. Commentary
    only; never touches pmt_forwarded/pmt_status_code/pmt_error. Defensive at the
    outermost level so nothing here can ever propagate into the background task
    runner, regardless of what fails. analyze_with_claude() is a blocking network
    call, so it's offloaded to a thread rather than run directly on the event loop -
    otherwise a slow Claude response would stall every other request this process is
    handling concurrently."""
    try:
        analysis, llm_error = await asyncio.to_thread(analyze_with_claude, payload)
    except Exception as e:
        analysis, llm_error = None, str(e)
    try:
        await repository.update_ai_analysis(
            correlation_id,
            settings.claude_model if analysis else None,
            analysis,
            llm_error,
        )
    except Exception:
        pass  # analysis is commentary only - a DB hiccup here must never surface as an error
    await event_bus.publish(event_types.TRADE_AI_ANALYZED, {
        "correlation_id": correlation_id, "ok": llm_error is None, "error": llm_error,
    })


@router.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    repository: TradeRepository = Depends(get_repository),
    event_bus: EventBus = Depends(get_event_bus),
):
    raw = await request.body()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)

    if settings.webhook_secret and payload.get("secret") != settings.webhook_secret:
        return JSONResponse({"ok": False, "error": "bad secret"}, status_code=401)

    event_type = payload.get("type", "entry")  # default to "entry" for backward compatibility
    correlation_id = payload.get("correlation_id")
    if not correlation_id:
        return JSONResponse({"ok": False, "error": "missing correlation_id"}, status_code=400)

    try:
        if event_type == "entry":
            return await _handle_entry(payload, raw, correlation_id, background_tasks, repository, event_bus)
        elif event_type == "price_update":
            return await _handle_price_update(payload, correlation_id, repository, event_bus)
        elif event_type == "exit":
            return await _handle_exit(payload, correlation_id, repository, event_bus)
        else:
            return JSONResponse({"ok": False, "error": f"unknown type: {event_type}"}, status_code=400)
    except Exception as e:
        logger.exception("webhook handling failed for correlation_id=%s", correlation_id)
        return JSONResponse({"ok": False, "error": f"db error: {e}"}, status_code=500)


async def _handle_entry(payload, raw, correlation_id, background_tasks, repository, event_bus):
    await event_bus.publish(event_types.TRADE_ENTRY_RECEIVED, {"correlation_id": correlation_id})
    raw_body = raw.decode("utf-8", errors="replace")

    async def do_forward():
        return await forward_to_pickmytrade(payload)

    result = await repository.claim_and_forward(correlation_id, payload, raw_body, do_forward)

    if result.duplicate:
        # Idempotency guard: this is a retry (TradingView redelivery, etc.) of a signal
        # that already placed a real order. Nothing was re-sent to PickMyTrade, the
        # existing record is untouched. Acknowledge so TradingView doesn't keep retrying.
        await event_bus.publish(event_types.TRADE_ENTRY_DUPLICATE, {"correlation_id": correlation_id})
        return JSONResponse(
            {"ok": True, "duplicate_already_forwarded": True, "correlation_id": correlation_id},
            status_code=208,
        )

    await event_bus.publish(
        event_types.TRADE_ENTRY_FORWARDED if result.forwarded else event_types.TRADE_ENTRY_FORWARD_FAILED,
        {"correlation_id": correlation_id, "pmt_status_code": result.pmt_status_code, "pmt_error": result.pmt_error},
    )

    # Claude runs after the response-critical work is done and does not block this
    # request at all - it's a background task, not part of the synchronous path.
    background_tasks.add_task(run_claude_analysis, payload, correlation_id, repository, event_bus)

    status_code = 200 if result.forwarded else 207
    return JSONResponse(
        {
            "ok": True,
            "pmt_forwarded": result.forwarded,
            "pmt_status_code": result.pmt_status_code,
            "pmt_error": result.pmt_error,
        },
        status_code=status_code,
    )


async def _handle_price_update(payload, correlation_id, repository, event_bus):
    matched = await repository.update_price(
        correlation_id, payload.get("current_price"), payload.get("unrealized_pnl"), now_iso()
    )
    if matched:
        await event_bus.publish(event_types.TRADE_PRICE_UPDATED, {
            "correlation_id": correlation_id,
            "current_price": payload.get("current_price"),
            "unrealized_pnl": payload.get("unrealized_pnl"),
        })
    return _matched_response(matched, correlation_id)


async def _handle_exit(payload, correlation_id, repository, event_bus):
    status = "won" if str(payload.get("outcome", "")).upper() == "WIN" else "lost"
    matched = await repository.update_exit(
        correlation_id, status, payload.get("exit_price"), payload.get("realized_pnl"), now_iso()
    )
    if matched:
        await event_bus.publish(event_types.TRADE_EXIT, {
            "correlation_id": correlation_id, "status": status,
            "realized_pnl": payload.get("realized_pnl"),
        })
    return _matched_response(matched, correlation_id)


def _matched_response(matched: int, correlation_id: str):
    if matched == 0:
        return JSONResponse(
            {"ok": True, "warning": f"no trade found for correlation_id {correlation_id}"}, status_code=200
        )
    return {"ok": True}

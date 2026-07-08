"""
POST /webhook (also mounted at /api/v1/webhook - see atlas/main.py). Same external
contract as Sprint 0: three event types keyed by "type", correlated by
"correlation_id", 200/207/208 response codes with the same meaning as before. This
module is orchestration only - the atomicity/idempotency guarantee lives in
TradeRepository.claim_and_forward, the PickMyTrade HTTP call lives in
atlas.services.pickmytrade, and the AI Copilot background tasks scheduled from here
(entry scoring on entry, post-trade review on exit) live in atlas.ai - see that
module's docstring for why they can never block or affect anything in this file's
response path.

Sprint 9 additions, all covered in docs/sprint9/security-notes.md:
  - The shared secret is compared in constant time and, when it IS blank (only
    possible in ENVIRONMENT=development - see atlas/config.py's
    Settings.validate_for_startup), no longer silently disables the check.
  - The payload is validated against a real schema (webhook_models.WebhookPayload)
    instead of raw dict access - malformed data is rejected (422), not silently
    tolerated by downstream code.
  - The secret is stripped out before the raw payload is ever persisted, so
    `trades.raw_entry_payload` can never leak it back out via GET /api/v1/trades.
  - When RISK_ENFORCEMENT=true, a breached kill switch blocks the PickMyTrade forward
    (not the DB write, not AI scoring - see _risk_enforcement_block_reason).
  - Rate limited (30/minute per IP) against webhook flooding.
"""
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from atlas.ai import run_entry_score, run_post_trade_review
from atlas.api.deps import get_event_bus, get_repository
from atlas.api.v1.webhook_models import WebhookPayload
from atlas.config import settings
from atlas.events import types as event_types
from atlas.events.bus import EventBus
from atlas.rate_limit import limiter
from atlas.repositories.base import TradeRepository
from atlas.risk import compute_risk_snapshot
from atlas.services.pickmytrade import forward_to_pickmytrade

logger = logging.getLogger("atlas.webhook")

router = APIRouter()

# Same generously-sized recent window atlas/api/v1/risk.py's own display-only snapshot
# already scans - enforcement and the dashboard can never disagree about what
# "breached" means, because it's the exact same function call over the exact same data.
RISK_SCAN_LIMIT = 1000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _secret_matches(provided: Optional[str], expected: str) -> bool:
    """Constant-time comparison. `expected` blank only happens in
    ENVIRONMENT=development (atlas.main:app refuses to start in production without a
    WEBHOOK_SECRET - see Settings.validate_for_startup), in which case every request
    is accepted, matching this project's existing local-dev convenience contract."""
    if not expected:
        return True
    if not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, expected)


def _sanitize_raw_body(raw_body: str) -> str:
    """The webhook secret must never be persisted (Sprint 9) - re-serializes the
    payload with the "secret" field removed rather than storing TradingView's literal
    bytes, so `trades.raw_entry_payload` (returned by GET /api/v1/trades) can never
    leak the shared secret. Falls back to the original text if it isn't a JSON object
    for some reason - defensive only, the caller has already parsed it successfully
    by the time this runs."""
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body
    if isinstance(data, dict) and "secret" in data:
        data = {k: v for k, v in data.items() if k != "secret"}
        return json.dumps(data)
    return raw_body


@router.post("/webhook")
@limiter.limit("30/minute")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    repository: TradeRepository = Depends(get_repository),
    event_bus: EventBus = Depends(get_event_bus),
):
    raw = await request.body()
    try:
        raw_json = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)

    provided_secret = raw_json.get("secret") if isinstance(raw_json, dict) else None
    if not _secret_matches(provided_secret, settings.webhook_secret):
        return JSONResponse({"ok": False, "error": "bad secret"}, status_code=401)

    try:
        validated = WebhookPayload.model_validate(raw_json)
    except ValidationError as e:
        # include_context=False: Pydantic's default .errors() embeds the raw
        # exception object for custom @field_validator failures (e.g. the
        # correlation_id/quantity checks below), which isn't JSON-serializable.
        details = e.errors(include_context=False)
        return JSONResponse({"ok": False, "error": "invalid payload", "details": details}, status_code=422)

    payload: dict[str, Any] = validated.model_dump()
    correlation_id = validated.correlation_id
    event_type = validated.type

    try:
        if event_type == "entry":
            return await _handle_entry(payload, raw, correlation_id, background_tasks, repository, event_bus)
        elif event_type == "price_update":
            return await _handle_price_update(payload, correlation_id, repository, event_bus)
        elif event_type == "exit":
            return await _handle_exit(payload, correlation_id, background_tasks, repository, event_bus)
        else:
            return JSONResponse({"ok": False, "error": f"unknown type: {event_type}"}, status_code=400)
    except Exception as e:
        logger.exception("webhook handling failed", extra={"correlation_id": correlation_id})
        return JSONResponse({"ok": False, "error": f"db error: {e}"}, status_code=500)


async def _risk_enforcement_block_reason(repository: TradeRepository) -> Optional[str]:
    """Only consulted when RISK_ENFORCEMENT=true - Settings.validate_for_startup
    already refused to start if that's set without real account limits configured, so
    this is never evaluated against placeholder numbers. Reuses the exact same
    atlas.risk.compute_risk_snapshot the display-only GET /api/v1/risk endpoint calls -
    enforcement and the dashboard can never disagree about what "breached" means.
    Never touches AI/analytics - this only decides what the `forward` callable passed
    to claim_and_forward returns; the trade itself is still stored and still scored
    exactly as if enforcement were off."""
    trades = await repository.list_recent(limit=RISK_SCAN_LIMIT)
    snapshot = compute_risk_snapshot(
        trades,
        starting_balance=settings.account_starting_balance,
        daily_loss_limit=settings.account_daily_loss_limit,
        trailing_drawdown_limit=settings.account_trailing_drawdown_limit,
        max_contracts=settings.account_max_contracts,
        point_value=settings.account_point_value,
        account_configured=settings.account_configured,
    )
    if snapshot.kill_switch.should_trigger:
        return "; ".join(snapshot.kill_switch.reasons)
    return None


async def _handle_entry(payload, raw, correlation_id, background_tasks, repository, event_bus):
    await event_bus.publish(event_types.TRADE_ENTRY_RECEIVED, {"correlation_id": correlation_id})
    raw_body = _sanitize_raw_body(raw.decode("utf-8", errors="replace"))

    async def do_forward():
        if settings.risk_enforcement:
            blocked_reason = await _risk_enforcement_block_reason(repository)
            if blocked_reason:
                return False, None, f"blocked by risk engine: {blocked_reason}"
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

    # AI entry scoring runs after the response-critical work is done and does not
    # block this request at all - it's a background task, not part of the synchronous
    # path. See atlas/ai.py for why this can never affect the response above.
    background_tasks.add_task(run_entry_score, payload, correlation_id, repository, event_bus)

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


async def _handle_exit(payload, correlation_id, background_tasks, repository, event_bus):
    status = "won" if str(payload.get("outcome", "")).upper() == "WIN" else "lost"
    matched = await repository.update_exit(
        correlation_id, status, payload.get("exit_price"), payload.get("realized_pnl"), now_iso()
    )
    if matched:
        await event_bus.publish(event_types.TRADE_EXIT, {
            "correlation_id": correlation_id, "status": status,
            "realized_pnl": payload.get("realized_pnl"),
        })
        # Same non-blocking discipline as entry scoring: scheduled as a background
        # task, runs after this response is already on its way out. Only scheduled
        # when the exit actually matched a stored trade - an unmatched exit has
        # nothing for a review to be about.
        background_tasks.add_task(run_post_trade_review, correlation_id, repository, event_bus)
    return _matched_response(matched, correlation_id)


def _matched_response(matched: int, correlation_id: str):
    if matched == 0:
        return JSONResponse(
            {"ok": True, "warning": f"no trade found for correlation_id {correlation_id}"}, status_code=200
        )
    return {"ok": True}

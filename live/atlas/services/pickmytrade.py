"""
PickMyTrade relay - forwards the order-placement fields of an entry event to the
webhook URL PickMyTrade gave you. This is the one call in the whole system that places
a real order, so it is deliberately simple (a single awaited HTTP call, no retry) and
is the only thing the entry path's response status depends on.

Async (unlike the Sprint 0 version, which used a blocking httpx.post) so it no longer
ties up the event loop for the duration of the call - this matters more now that it
runs inside PostgresTradeRepository.claim_and_forward's transaction, holding a pooled
connection and an advisory lock for that same duration.

Diagnostics (added for E2E integration-test debugging - PickMyTrade's own Alert Log
was showing nothing for a relay Atlas believed succeeded): every attempt is logged in
full via structured logging (see atlas/logging_config.py - these fields land as real
JSON fields in Railway's log viewer, not buried in a message string), and the caller
can optionally pass a `diagnostics` dict to have it populated in place with the same
data, for persisting alongside the trade (see atlas/api/v1/webhook.py). This is
deliberately an optional output parameter rather than a change to ForwardResult's
shape - forward_to_pickmytrade's 3-tuple return is depended on by ~25 existing test
mocks and both repository implementations' claim_and_forward; adding diagnostics this
way changes nothing about what already exists, it only adds.

None of this changes relay behavior: the same URL, same payload fields, same 15s
timeout, same success/failure classification (status < 400) as before - purely
observability wrapped around the unchanged call.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from atlas.config import settings

logger = logging.getLogger("atlas.pickmytrade")

PMT_FIELDS = [
    "symbol", "strategy_name", "date", "data", "quantity", "price", "tp", "sl",
    "trail", "trail_stop", "trail_trigger", "trail_freq", "token", "pyramid",
    "same_direction_ignore", "reverse_order_close", "multiple_accounts",
]

# Bounds on what gets persisted to the trades table (Railway logs get the untruncated
# response body - only the stored copy is capped, to keep a single misbehaving
# response - e.g. an HTML error page - from bloating a trade row unboundedly).
STORED_RESPONSE_BODY_LIMIT = 4000

ForwardResult = tuple[bool, Optional[int], Optional[str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _mask_token(token: Any) -> Any:
    if not isinstance(token, str) or not token:
        return token
    return f"***{token[-4:]}" if len(token) > 4 else "***"


def _mask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Deep-enough copy that masks every credential field without touching anything
    else - `token` at the top level and inside each entry of `multiple_accounts`."""
    masked = dict(payload)
    if "token" in masked:
        masked["token"] = _mask_token(masked["token"])
    if isinstance(masked.get("multiple_accounts"), list):
        masked["multiple_accounts"] = [
            {**acct, "token": _mask_token(acct.get("token"))} if isinstance(acct, dict) else acct
            for acct in masked["multiple_accounts"]
        ]
    return masked


async def forward_to_pickmytrade(
    payload: dict[str, Any], *, diagnostics: Optional[dict[str, Any]] = None,
) -> ForwardResult:
    """Returns (forwarded: bool, status_code: int|None, error: str|None) - unchanged
    from before. If `diagnostics` is provided, it's populated in place with url,
    method, masked payload, status_code, response_body, exception, and duration_ms -
    the caller decides what to do with it (see atlas/api/v1/webhook.py)."""
    pmt_payload = {k: payload[k] for k in PMT_FIELDS if k in payload}
    masked_payload = _mask_payload(pmt_payload)
    attempted_at = _now_iso()
    url = settings.pickmytrade_webhook_url

    def _record(*, status_code, response_body, exception, duration_ms):
        record = {
            "attempted_at": attempted_at,
            "url": url or None,
            "method": "POST",
            "payload": masked_payload,
            "status_code": status_code,
            "response_body": response_body,
            "exception": exception,
            "duration_ms": round(duration_ms, 1),
        }
        if diagnostics is not None:
            diagnostics.update(record)
        return record

    if not url:
        _record(status_code=None, response_body=None, exception="PICKMYTRADE_WEBHOOK_URL not configured", duration_ms=0.0)
        logger.warning("pickmytrade relay skipped - not configured", extra={"pmt_url": None})
        return False, None, "PICKMYTRADE_WEBHOOK_URL not configured"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=pmt_payload)
        duration_ms = (time.monotonic() - start) * 1000
        response_body = resp.text
        error = None if resp.status_code < 400 else f"HTTP {resp.status_code}: {response_body[:200]}"

        record = _record(
            status_code=resp.status_code,
            response_body=response_body[:STORED_RESPONSE_BODY_LIMIT],
            exception=None,
            duration_ms=duration_ms,
        )
        log_fn = logger.info if error is None else logger.warning
        log_fn(
            "pickmytrade relay attempt",
            extra={
                "pmt_url": record["url"], "pmt_method": record["method"], "pmt_payload": masked_payload,
                "pmt_status_code": resp.status_code, "pmt_response_body": response_body,
                "pmt_duration_ms": record["duration_ms"],
            },
        )
        return True, resp.status_code, error
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        record = _record(status_code=None, response_body=None, exception=str(e), duration_ms=duration_ms)
        logger.warning(
            "pickmytrade relay failed",
            extra={
                "pmt_url": record["url"], "pmt_method": record["method"], "pmt_payload": masked_payload,
                "pmt_exception": str(e), "pmt_duration_ms": record["duration_ms"],
            },
        )
        return False, None, str(e)

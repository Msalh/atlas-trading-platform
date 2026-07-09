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

Field normalization (confirmed via a direct curl test bypassing Atlas entirely - see
docs discussion, not reproduced here): PickMyTrade's own documented/example payloads
use lowercase "buy"/"sell" for `data`, a quoted string for `price` (their examples
source it from TradingView's {{close}} placeholder, which only ever substitutes as
text), and an ISO-8601 UTC string for `date` (from {{timenow}}, likewise always text).
Atlas's internal payload (built in the Pine strategy, untouched by this) never matched
any of the three - PickMyTrade accepted every relay ("Successfully send") without ever
creating an Alert Log entry or order. An identical payload with these three fields
normalized, sent directly to PickMyTrade, was correctly recognized (status
TradingLocked - rejected only because the connected account is locked, not because the
payload was malformed). Normalizing happens ONLY here, at the outbound-to-PickMyTrade
boundary - `data`/`price`/`date` are PickMyTrade-specific fields Atlas's own internal
logic (risk/AI/analytics, all keyed off `direction`/`entry_price`) never reads, so this
cannot affect anything upstream. tp/sl stay numeric - PickMyTrade's own examples show
them as plain numbers, not strings.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from atlas.config import settings

logger = logging.getLogger("atlas.pickmytrade")

PMT_FIELDS = [
    # `strategy_name` deliberately excluded (Sprint - PMT payload parity): a direct
    # curl test against PickMyTrade's live endpoint, verified end-to-end (status
    # TradingLocked - correctly recognized, just blocked by account state), did not
    # include this field at all. Atlas's own internal storage/trade record still keeps
    # strategy_name (see WebhookPayload/payload dict) - this list only controls what's
    # forwarded to PickMyTrade specifically.
    "symbol", "date", "data", "quantity", "price", "tp", "sl",
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


def _to_iso_utc(date_value: Any) -> str:
    """Converts Atlas's internal `date` (TradingView epoch-milliseconds, sent as a
    string - see the Pine strategy's toJson) to the ISO-8601 UTC string PickMyTrade's
    own examples use. Falls back to the current time if the value is missing or isn't
    a valid epoch-millisecond string, rather than ever failing the relay over a
    formatting hiccup in a field PickMyTrade doesn't use for order routing."""
    try:
        dt = datetime.fromtimestamp(int(date_value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_pmt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """See this module's docstring for why - `data` lowercased, `price` stringified,
    `date` converted to ISO-8601 UTC. tp/sl are deliberately left untouched."""
    normalized = dict(payload)
    if isinstance(normalized.get("data"), str):
        normalized["data"] = normalized["data"].lower()
    if normalized.get("price") is not None:
        normalized["price"] = str(normalized["price"])
    if "date" in normalized:
        normalized["date"] = _to_iso_utc(normalized.get("date"))
    return normalized


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
    pmt_payload = _normalize_pmt_payload(pmt_payload)
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

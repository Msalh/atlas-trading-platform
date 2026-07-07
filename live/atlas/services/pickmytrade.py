"""
PickMyTrade relay - forwards the order-placement fields of an entry event to the
webhook URL PickMyTrade gave you. This is the one call in the whole system that places
a real order, so it is deliberately simple (a single awaited HTTP call, no retry) and
is the only thing the entry path's response status depends on.

Async (unlike the Sprint 0 version, which used a blocking httpx.post) so it no longer
ties up the event loop for the duration of the call - this matters more now that it
runs inside PostgresTradeRepository.claim_and_forward's transaction, holding a pooled
connection and an advisory lock for that same duration.
"""
from typing import Any, Optional

import httpx

from atlas.config import settings

PMT_FIELDS = [
    "symbol", "strategy_name", "date", "data", "quantity", "price", "tp", "sl",
    "trail", "trail_stop", "trail_trigger", "trail_freq", "token", "pyramid",
    "same_direction_ignore", "reverse_order_close", "multiple_accounts",
]

ForwardResult = tuple[bool, Optional[int], Optional[str]]


async def forward_to_pickmytrade(payload: dict[str, Any]) -> ForwardResult:
    """Returns (forwarded: bool, status_code: int|None, error: str|None)."""
    if not settings.pickmytrade_webhook_url:
        return False, None, "PICKMYTRADE_WEBHOOK_URL not configured"
    pmt_payload = {k: payload[k] for k in PMT_FIELDS if k in payload}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(settings.pickmytrade_webhook_url, json=pmt_payload)
        error = None if resp.status_code < 400 else f"HTTP {resp.status_code}: {resp.text[:200]}"
        return True, resp.status_code, error
    except Exception as e:
        return False, None, str(e)

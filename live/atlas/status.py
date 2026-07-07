"""
In-process, best-effort system status tracker for the Connection Status UI panel.
Subscribes to every event type on the EventBus (see atlas/main.py's lifespan) and
records when each was last seen, and the payload it fired with.

Deliberately NOT persisted - it answers "is this process currently hearing from
TradingView / talking to PickMyTrade / talking to Claude", which resets meaningfully
on every deploy (a fresh process legitimately hasn't heard from anything yet). This is
different from "what actually happened to trade X historically", which already lives
in the `trades` table and is read directly by the trades endpoints instead - this
class exists purely for liveness, not as a system of record.
"""
from datetime import datetime, timezone
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SystemStatus:
    def __init__(self):
        self._last_event_at: dict[str, str] = {}
        self._last_event_payload: dict[str, dict[str, Any]] = {}

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self._last_event_at[event_type] = now_iso()
        self._last_event_payload[event_type] = payload

    def last_at(self, event_type: str) -> Optional[str]:
        return self._last_event_at.get(event_type)

    def last_payload(self, event_type: str) -> Optional[dict[str, Any]]:
        return self._last_event_payload.get(event_type)

    def most_recent(self, event_types: list[str]) -> tuple[Optional[str], Optional[str]]:
        """Returns (event_type, timestamp) for whichever of the given event types was
        last seen most recently, or (None, None) if none of them have fired yet."""
        candidates = [(et, self._last_event_at[et]) for et in event_types if et in self._last_event_at]
        if not candidates:
            return None, None
        event_type, timestamp = max(candidates, key=lambda pair: pair[1])
        return event_type, timestamp

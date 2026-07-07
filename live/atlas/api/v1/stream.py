"""
GET /api/v1/stream - Server-Sent Events feed of trade lifecycle events, so the
frontend can react sooner than its normal poll interval instead of waiting for the
next scheduled refetch.

Deliberately thin: events on the wire carry only {type, ...whatever the EventBus
payload already had} - never a full trade row. The frontend treats every event as
"something changed, go refetch the relevant REST endpoint" (via React Query cache
invalidation) rather than as the source of truth itself. This keeps exactly one
serialization path (the REST endpoints from Sprint 2) instead of two that could drift
out of sync with each other.

Polling remains the source of truth and the fallback, not SSE - if a client's stream
disconnects, its own polling (at a shorter interval - see the frontend's
lib/intervals.ts) picks up the slack without any coordination with this endpoint. This
endpoint has no memory of what a reconnecting client missed; it only ever emits events
published *while it is connected*, exactly like a live radio broadcast.
"""
import asyncio
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from atlas.api.deps import get_event_bus
from atlas.events.bus import EventBus
from atlas.events.types import ALL as ALL_EVENT_TYPES

logger = logging.getLogger("atlas.stream")

router = APIRouter()

KEEPALIVE_SECONDS = 15
CLIENT_QUEUE_MAXSIZE = 100


def sse_format(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def event_stream(
    event_bus: EventBus, is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """The actual streaming logic, decoupled from FastAPI's Request object so it can
    be unit-tested directly (see tests/test_stream.py) without spinning up a real HTTP
    connection."""
    queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue(maxsize=CLIENT_QUEUE_MAXSIZE)

    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        try:
            queue.put_nowait({"type": event_type, **payload})
        except asyncio.QueueFull:
            # A stuck/slow client must never block publish() for every other
            # subscriber (other SSE clients, the logger, SystemStatus). It will
            # simply miss this one event - its own polling fallback covers the gap.
            logger.warning("SSE client queue full, dropping event %s", event_type)

    for event_type in ALL_EVENT_TYPES:
        event_bus.subscribe(event_type, handler)

    try:
        yield sse_format("connected", {"ok": True})
        while True:
            if await is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                yield sse_format("trade", event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # SSE comment line - ignored by EventSource, keeps proxies from timing out the connection
    finally:
        for event_type in ALL_EVENT_TYPES:
            event_bus.unsubscribe(event_type, handler)


@router.get("/stream")
async def stream(request: Request, event_bus: EventBus = Depends(get_event_bus)):
    return StreamingResponse(
        event_stream(event_bus, request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy response buffering (nginx/Railway edge) so events aren't queued up before delivery
        },
    )

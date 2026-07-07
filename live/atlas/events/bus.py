"""
In-process async publish/subscribe event bus.

This exists so that new consumers of trade lifecycle events (Discord/Telegram/Email
notifications, a future SSE broadcast to the frontend, additional analytics) can be
added later purely by calling `event_bus.subscribe(...)` at startup - without ever
touching the webhook/execution code that publishes the events. Publishing is
fire-and-forget from the publisher's point of view: a broken or slow subscriber can
never delay or fail the request that published the event, because every subscriber
call is isolated and its exception is logged, never re-raised to the caller.

This is deliberately not a message queue (no persistence, no delivery guarantee across
restarts) - it is a same-process fan-out, which is all a single FastAPI instance needs
today. If Atlas ever runs as multiple instances behind a load balancer, this is the
seam where a real broker (e.g. Redis pub/sub) would replace this class without
changing anything that calls `publish`/`subscribe`.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger("atlas.events")

Handler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """No-op if the handler is already gone. Callers that subscribe per-connection
        (e.g. one SSE client) must unsubscribe on disconnect - otherwise every past
        connection's handler stays registered forever, leaking memory and doing
        wasted work on every future publish()."""
        handlers = self._subscribers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        handlers = self._subscribers.get(event_type, ())
        if not handlers:
            return
        results = await asyncio.gather(
            *(handler(event_type, payload) for handler in handlers),
            return_exceptions=True,
        )
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "event subscriber failed: event=%s handler=%s error=%s",
                    event_type, getattr(handler, "__qualname__", handler), result,
                )

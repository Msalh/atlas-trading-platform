"""Small per-process limiter for the single-instance private API."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException


class FixedWindowRateLimiter:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        window_seconds: float = 60.0,
    ) -> None:
        self._clock = clock
        self._window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int) -> None:
        now = self._clock()
        events = self._events[key]
        cutoff = now - self._window
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        events.append(now)

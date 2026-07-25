"""Small RFC 9562 UUIDv7 generator with injectable time and randomness."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID


def generate_uuid7(
    *,
    now: Callable[[], datetime],
    randbits: Callable[[int], int] = secrets.randbits,
) -> str:
    instant = now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("UUIDv7 clock must be timezone-aware")
    milliseconds = int(instant.astimezone(timezone.utc).timestamp() * 1000)
    if not 0 <= milliseconds < 2**48:
        raise ValueError("UUIDv7 timestamp is out of range")
    random_a = randbits(12)
    random_b = randbits(62)
    if not 0 <= random_a < 2**12 or not 0 <= random_b < 2**62:
        raise ValueError("UUIDv7 randomness source returned an invalid value")
    value = (
        (milliseconds << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return str(UUID(int=value))

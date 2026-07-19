"""
UTC time helpers. Deliberately minimal: this module knows nothing about trading
sessions, market hours, or holidays - that is atlas.market_engine's domain, built
against real session-boundary requirements, not guessed at here. This module only
enforces one rule project-wide: a "timestamp" in this system is always a
timezone-aware UTC datetime, never a naive one.

now_utc()'s ISO format matches the convention already established in
atlas/repositories/memory.py, atlas/repositories/postgres.py, and
atlas/api/v1/webhook.py (`datetime.now(timezone.utc).isoformat(timespec="seconds")`)
- reused here as the one place that convention is defined, not duplicated a fourth
time. Those three existing call sites are left unchanged in this Sprint (see the
Sprint 1 retrospective for why); a future, separately-scoped Sprint may point them
at this function instead.
"""
from datetime import datetime, timezone

from atlas.core.errors import NaiveDatetimeError


def now_utc() -> datetime:
    """The current time, as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    """The current time as an ISO-8601 string, seconds precision - matches the
    existing now_iso() convention exactly."""
    return now_utc().isoformat(timespec="seconds")


def require_utc(value: datetime) -> datetime:
    """Raises NaiveDatetimeError if `value` has no timezone attached. Returns
    `value` unchanged otherwise - callers use this as a validation gate, not a
    converter, because silently assuming a naive datetime means UTC has already
    been the source of subtle bugs in adjacent systems (see the SD-1 holiday/DST
    findings in tools/research) - better to reject than guess."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise NaiveDatetimeError(
            f"expected a timezone-aware datetime, got a naive one: {value!r}. "
            f"This system never assumes a naive datetime means UTC - attach an "
            f"explicit timezone before passing it in."
        )
    return value

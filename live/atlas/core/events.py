"""
The base event envelope every future domain event (market_engine bar/session
events, journal entries, and anything else event-shaped) builds on. Deliberately
carries no payload-shape assumptions - what an event's data looks like is each
future event type's own concern; this module only fixes the shared envelope
fields every one of them needs regardless of type: an id, a type name, where it
came from, when it happened, and when this system learned about it.

occurred_at vs. received_at is not a naming nicety - it is the single most
load-bearing distinction in the whole event-store design (see the project
architecture review): occurred_at is when the event happened in the world;
received_at is when this system found out. Replay correctness depends on never
conflating the two.
"""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from atlas.core.errors import AtlasDomainError
from atlas.core.time import now_utc, require_utc


@dataclass(frozen=True)
class Event:
    """The base envelope. Concrete event types compose this rather than
    inheriting a payload shape from it - see this module's docstring."""

    event_type: str
    source: str
    occurred_at: datetime
    received_at: datetime = field(default_factory=now_utc)
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.event_type or not self.event_type.strip():
            raise AtlasDomainError("event_type must not be blank")
        if not self.source or not self.source.strip():
            raise AtlasDomainError("source must not be blank")
        require_utc(self.occurred_at)
        require_utc(self.received_at)

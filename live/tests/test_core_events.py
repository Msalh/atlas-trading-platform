from datetime import datetime, timezone

import pytest

from atlas.core.errors import AtlasDomainError, NaiveDatetimeError
from atlas.core.events import Event


def _aware(dt_str="2026-07-18T12:00:00"):
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)


class TestEvent:
    def test_minimal_construction(self):
        e = Event(event_type="bar_closed", source="tradingview", occurred_at=_aware())
        assert e.event_type == "bar_closed"
        assert e.source == "tradingview"
        assert e.occurred_at == _aware()

    def test_event_id_auto_generated_and_unique(self):
        e1 = Event(event_type="bar_closed", source="tradingview", occurred_at=_aware())
        e2 = Event(event_type="bar_closed", source="tradingview", occurred_at=_aware())
        assert e1.event_id != e2.event_id
        assert e1.event_id  # non-empty

    def test_received_at_defaults_to_now(self):
        before = datetime.now(timezone.utc)
        e = Event(event_type="bar_closed", source="tradingview", occurred_at=_aware())
        after = datetime.now(timezone.utc)
        assert before <= e.received_at <= after

    def test_occurred_at_and_received_at_are_independently_settable(self):
        # this is the single most load-bearing distinction in the event store -
        # an event ingested late must be able to say so.
        occurred = _aware("2026-07-18T09:00:00")
        received = _aware("2026-07-18T09:05:00")
        e = Event(event_type="bar_closed", source="tradingview", occurred_at=occurred, received_at=received)
        assert e.occurred_at != e.received_at
        assert e.received_at > e.occurred_at

    def test_naive_occurred_at_rejected(self):
        with pytest.raises(NaiveDatetimeError):
            Event(event_type="bar_closed", source="tradingview", occurred_at=datetime(2026, 7, 18, 12, 0, 0))

    def test_naive_received_at_rejected(self):
        with pytest.raises(NaiveDatetimeError):
            Event(
                event_type="bar_closed",
                source="tradingview",
                occurred_at=_aware(),
                received_at=datetime(2026, 7, 18, 12, 0, 0),
            )

    def test_blank_event_type_rejected(self):
        with pytest.raises(AtlasDomainError):
            Event(event_type="", source="tradingview", occurred_at=_aware())

    def test_blank_source_rejected(self):
        with pytest.raises(AtlasDomainError):
            Event(event_type="bar_closed", source="", occurred_at=_aware())

    def test_immutable(self):
        e = Event(event_type="bar_closed", source="tradingview", occurred_at=_aware())
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            e.event_type = "something_else"

    def test_out_of_order_occurred_at_is_not_itself_an_error(self):
        # Event is a pure value type - deciding what "stale" or "out of order"
        # MEANS relative to other events is market_engine's job (a later
        # Sprint), not this envelope's. Constructing an event with an
        # occurred_at far in the past must succeed here.
        old = _aware("2020-01-01T00:00:00")
        e = Event(event_type="bar_closed", source="tradingview", occurred_at=old)
        assert e.occurred_at == old

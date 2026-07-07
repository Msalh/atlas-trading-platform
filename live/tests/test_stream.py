"""
Tests for the SSE event_stream generator (atlas/api/v1/stream.py). These drive the
generator directly rather than going through a real HTTP connection - event_stream()
takes a plain `is_disconnected` callable instead of a FastAPI Request specifically so
it can be unit-tested this way, without the complexity of coordinating a background
event loop (TestClient) with the test's own async publish calls.
"""
import asyncio

import pytest

import atlas.api.v1.stream as stream_module
from atlas.events.bus import EventBus
from atlas.events.types import ALL as ALL_EVENT_TYPES
from atlas.events.types import TRADE_ENTRY_RECEIVED, TRADE_EXIT


class DisconnectSignal:
    """A controllable stand-in for FastAPI's Request.is_disconnected."""

    def __init__(self):
        self._disconnected = False

    async def __call__(self) -> bool:
        return self._disconnected

    def disconnect(self) -> None:
        self._disconnected = True


def test_sse_format_produces_valid_wire_format():
    chunk = stream_module.sse_format("trade", {"type": "trade.exit", "correlation_id": "x"})
    assert chunk.startswith("event: trade\ndata: ")
    assert chunk.endswith("\n\n")
    assert '"correlation_id": "x"' in chunk


async def test_stream_yields_a_connected_event_first():
    bus = EventBus()
    signal = DisconnectSignal()
    gen = stream_module.event_stream(bus, signal)

    first = await gen.__anext__()

    assert "event: connected" in first
    assert '"ok": true' in first

    signal.disconnect()
    await gen.aclose()


async def test_stream_forwards_published_events():
    bus = EventBus()
    signal = DisconnectSignal()
    gen = stream_module.event_stream(bus, signal)
    await gen.__anext__()  # consume "connected"

    async def publish_soon():
        await asyncio.sleep(0.01)
        await bus.publish(TRADE_ENTRY_RECEIVED, {"correlation_id": "corr-1"})

    publish_task = asyncio.create_task(publish_soon())
    chunk = await gen.__anext__()
    await publish_task

    assert "event: trade" in chunk
    assert "trade.entry.received" in chunk
    assert "corr-1" in chunk

    signal.disconnect()
    await gen.aclose()


async def test_stream_sends_keepalive_when_no_events_arrive(monkeypatch):
    monkeypatch.setattr(stream_module, "KEEPALIVE_SECONDS", 0.05)
    bus = EventBus()
    signal = DisconnectSignal()
    gen = stream_module.event_stream(bus, signal)
    await gen.__anext__()  # "connected"

    chunk = await gen.__anext__()

    assert chunk == ": keepalive\n\n"
    signal.disconnect()
    await gen.aclose()


async def test_stream_stops_when_client_disconnects():
    bus = EventBus()
    signal = DisconnectSignal()
    gen = stream_module.event_stream(bus, signal)
    await gen.__anext__()  # "connected"

    signal.disconnect()

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


async def test_stream_unsubscribes_all_event_types_on_disconnect():
    bus = EventBus()
    signal = DisconnectSignal()
    gen = stream_module.event_stream(bus, signal)
    await gen.__anext__()  # "connected" - subscriptions are registered by this point

    for event_type in ALL_EVENT_TYPES:
        assert len(bus._subscribers[event_type]) == 1

    signal.disconnect()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    for event_type in ALL_EVENT_TYPES:
        assert len(bus._subscribers.get(event_type, [])) == 0


async def test_stream_drops_events_for_a_full_queue_without_raising(monkeypatch):
    monkeypatch.setattr(stream_module, "CLIENT_QUEUE_MAXSIZE", 1)
    bus = EventBus()
    signal = DisconnectSignal()
    gen = stream_module.event_stream(bus, signal)
    await gen.__anext__()  # "connected"

    # Two publishes before the client ever reads from the queue - the second must be
    # dropped silently (queue maxsize=1), not raise into publish().
    await bus.publish(TRADE_EXIT, {"correlation_id": "a"})
    await bus.publish(TRADE_EXIT, {"correlation_id": "b"})

    chunk = await gen.__anext__()
    assert '"correlation_id": "a"' in chunk

    signal.disconnect()
    await gen.aclose()

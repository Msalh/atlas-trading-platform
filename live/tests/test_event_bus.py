"""Unit tests for the EventBus - the pub/sub mechanism new subscribers (notifications,
future SSE broadcast, etc.) will attach to without ever touching the code that
publishes events."""
import asyncio

from atlas.events.bus import EventBus


def test_publish_calls_all_subscribers_for_the_event_type():
    bus = EventBus()
    received = []

    async def handler_a(event_type, payload):
        received.append(("a", event_type, payload))

    async def handler_b(event_type, payload):
        received.append(("b", event_type, payload))

    bus.subscribe("trade.entry.forwarded", handler_a)
    bus.subscribe("trade.entry.forwarded", handler_b)
    bus.subscribe("trade.exit", handler_a)

    asyncio.run(bus.publish("trade.entry.forwarded", {"correlation_id": "x"}))

    assert ("a", "trade.entry.forwarded", {"correlation_id": "x"}) in received
    assert ("b", "trade.entry.forwarded", {"correlation_id": "x"}) in received
    assert len(received) == 2  # the "trade.exit" subscription must not fire


def test_publish_with_no_subscribers_is_a_no_op():
    bus = EventBus()
    asyncio.run(bus.publish("nobody.listening", {}))  # must not raise


def test_a_failing_subscriber_does_not_prevent_others_from_running_or_raise():
    bus = EventBus()
    received = []

    async def broken_handler(event_type, payload):
        raise RuntimeError("simulated subscriber bug")

    async def working_handler(event_type, payload):
        received.append(payload)

    bus.subscribe("trade.exit", broken_handler)
    bus.subscribe("trade.exit", working_handler)

    asyncio.run(bus.publish("trade.exit", {"correlation_id": "y"}))  # must not raise

    assert received == [{"correlation_id": "y"}]


def test_unsubscribe_stops_further_delivery():
    bus = EventBus()
    received = []

    async def handler(event_type, payload):
        received.append(payload)

    bus.subscribe("trade.exit", handler)
    asyncio.run(bus.publish("trade.exit", {"n": 1}))
    bus.unsubscribe("trade.exit", handler)
    asyncio.run(bus.publish("trade.exit", {"n": 2}))

    assert received == [{"n": 1}]


def test_unsubscribe_of_a_never_subscribed_handler_is_a_no_op():
    bus = EventBus()

    async def handler(event_type, payload):
        pass

    bus.unsubscribe("trade.exit", handler)  # must not raise

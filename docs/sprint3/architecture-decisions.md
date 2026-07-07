# Sprint 3 - Architecture Decisions

## 1. SSE carries invalidation signals, not data
Events on the wire are `{type, ...whatever the EventBus payload already had}` -
`correlation_id` plus a few small fields, never a full trade row. The frontend's
`LiveUpdatesProvider` treats every event as "something changed, go refetch" and calls
`queryClient.invalidateQueries` for the affected query-key groups, reusing the exact same
REST endpoints and serialization Sprint 2 already built and tested. The alternative
(streaming full trade payloads over SSE) would need a second serialization path that could
drift from the REST responses - not worth it for a sprint explicitly scoped as "real-time
updates foundation," not a full data-sync protocol.

## 2. Polling never stops - "fallback" means "safety net," not "backup transport"
Every `useQuery` in the frontend keeps a `refetchInterval` at all times. When SSE is
connected, `lib/intervals.ts::pollInterval` multiplies the base interval by 6x (e.g. current
position goes from 5s to 30s) rather than disabling it. This means:
- A dropped/malformed SSE event (e.g. a full client queue on the backend, see #4) is silently
  corrected within one poll cycle, not left stale indefinitely.
- There's no separate "SSE reconnected, now do a catch-up fetch" code path to get wrong -
  the next scheduled poll (at most `base * 6` away) does that job automatically.
- If SSE is unreachable for an entire session (corporate proxy strips it, etc.), the app
  degrades to exactly Sprint 2's behavior with no code branch difference.

## 3. `event_stream()` takes a callable, not a `Request`
`atlas/api/v1/stream.py::event_stream(event_bus, is_disconnected)` is deliberately decoupled
from FastAPI's `Request` object (the route wrapper passes `request.is_disconnected` as the
callable). This is what makes `tests/test_stream.py` possible without standing up a real HTTP
connection or coordinating two event loops (the test's and TestClient's background thread) -
tests drive the generator directly with a controllable fake, publish events into a real
`EventBus`, and assert on the exact strings yielded. Same testability principle as Sprint 1's
`TradeRepository` interface (real implementation vs. test double).

## 4. A slow/stuck SSE client must never block anyone else
Each connection gets its own bounded `asyncio.Queue` (`CLIENT_QUEUE_MAXSIZE = 100`). If a
client stops reading (dead browser tab, network black hole) and its queue fills up, new
events for that client are dropped silently (`asyncio.QueueFull` caught, logged, swallowed) -
`EventBus.publish` itself already isolates every subscriber from every other one (Sprint 1),
this is the same principle applied to a per-connection consumer. A client that catches up
this way relies on its own polling fallback (#2) to correct any gap, exactly as designed.

## 5. `EventBus.unsubscribe` - new, required by SSE, not previously needed
Sprint 1/2's only subscribers (`log_event`, `SystemStatus.record`) were registered once at
startup and lived for the process's whole lifetime - nothing ever needed to detach. SSE
subscribes a fresh handler *per connection* and must remove it on disconnect, or every past
visitor's handler stays registered forever (memory leak, and wasted work broadcasting to
dead handlers on every future `publish()`). Added `EventBus.unsubscribe` and covered it with
its own unit tests plus an end-to-end check in `test_stream.py` that a stream's handler
count returns to zero after disconnect.

## 6. No new event types, no webhook changes
`ALL_EVENT_TYPES` (`atlas/events/types.py`) is unchanged from Sprint 1/2. The SSE endpoint
subscribes to exactly the same events `SystemStatus` already does. Nothing in
`atlas/api/v1/webhook.py` changed this sprint - satisfies "do not change webhook payloads /
PickMyTrade relay semantics" by construction, not by discipline alone.

## 7. Visible "live / polling" indicator
`HeaderStatusDot` now shows "● live" / "○ polling" based on `useLiveUpdatesConnected()`, in
addition to the existing DB health dot. This was not an explicit deliverable but is a
one-line addition that makes the sprint's actual feature (does real-time work right now?)
directly observable instead of only inferable from network behavior - worth keeping.

## 8. Verified with a real live push, not just unit tests
Beyond the 9 new backend tests, this sprint's manual verification (see
docs/sprint3/deployment-checklist.md) sent a real webhook entry to the running dev server
while the dashboard was open and confirmed - via screenshot - that Current Position, Trade
History, Connection Status, and Today's stats all updated without a page refresh or waiting
for a poll tick. Reconnect behavior was verified the same way: stopping the backend flipped
the indicator to "○ polling," restarting it flipped back to "● live" via the browser's native
`EventSource` retry, no custom reconnect logic needed on the frontend.

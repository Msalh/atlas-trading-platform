# Sprint 3 - API Contract Addendum

## `GET /api/v1/stream`
Server-Sent Events (`text/event-stream`). No query params, no auth (matches every other
`/api/v1/*` read endpoint - see Sprint 2's addendum). Held open indefinitely until the client
disconnects or the server process restarts.

### Wire format
```
event: connected
data: {"ok": true}

event: trade
data: {"type": "trade.entry.received", "correlation_id": "2026-07-07T17:35:00Z"}

: keepalive

```
- **`connected`** - sent once, immediately on connect. Purely informational (lets a client
  distinguish "just opened, no events yet" from "actually broken").
- **`trade`** - sent once per published EventBus event, for every event type in
  `atlas/events/types.py` (`trade.entry.received`, `trade.entry.forwarded`,
  `trade.entry.forward_failed`, `trade.entry.duplicate`, `trade.price_updated`,
  `trade.exit`, `trade.ai_analyzed`). `data` is `{"type": "<event type>", ...event
  payload}` - the payload shape matches whatever that event type already carries
  internally (see `atlas/api/v1/webhook.py` for what each `event_bus.publish(...)` call
  sends). **Not guaranteed to contain every field of the affected trade** - treat this as
  "something changed for this correlation_id, refetch `/api/v1/trades/{id}` or
  `/api/v1/trades/current`," not as the full record.
- **`: keepalive`** (an SSE comment line, no `event:`/`data:`) - sent every 15s when nothing
  else has happened, so intermediate proxies/load balancers don't time out an idle
  connection. Clients should ignore comment lines (the native `EventSource` API does this
  automatically).

### What a client should do with each event
| Event type | Suggested reaction |
|---|---|
| any `trade.*` | refetch `/api/v1/trades/current` and `/api/v1/trades` (current position + history) |
| any `trade.*` | refetch `/api/v1/status` (every event type affects some field there) |
| `trade.entry.received`, `trade.exit` | also refetch `/api/v1/stats/today` |
| any `trade.*`, if a trade detail view for that `correlation_id` is open | refetch `/api/v1/trades/{correlation_id}` |

This is exactly what `frontend/src/lib/live-updates.tsx::queryKeyGroupsFor` implements via
React Query's prefix-matching `invalidateQueries`.

### Guarantees this endpoint does NOT make
- **No replay.** A client that connects, disconnects, and reconnects will not receive events
  published while it was disconnected. Polling (still active on every client at all times -
  see architecture-decisions.md #2) is what closes that gap, not this endpoint.
- **No delivery guarantee even while connected.** A sufficiently slow client can have events
  dropped (bounded per-connection queue, see architecture-decisions.md #4). Same polling
  fallback applies.
- **No authentication.** Same as the rest of `/api/v1/*` - read-only, no secrets in the
  payloads. Revisit alongside the rest of the API if that changes.

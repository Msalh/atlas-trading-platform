# Sprint 1 - Architecture Decisions

## 1. Postgres now, not later
Railway's SQLite volume is one misconfigured mount away from losing all trade history, and
SQLite serializes writers - fine for a single webhook source, not fine once ingestion,
background AI writes, and dashboard reads happen concurrently. Migrating now, while the
schema is small and nothing else depends on SQLite-specific behavior, is far cheaper than
migrating after months of trade history and a live frontend. This was already the plan from
the approved V2 architecture; Sprint 1 executes it.

## 2. Modular monolith, not microservices
`atlas/` is one deployable FastAPI process with clean internal package boundaries
(`repositories`, `services`, `events`, `api`). No network calls between internal components.
This is deliberate - splitting into services now would add distributed-systems overhead
(service discovery, network failure modes, distributed tracing) with no corresponding
benefit at this scale.

## 3. Repository interface as a `Protocol`, not an ABC with inheritance
`atlas/repositories/base.py` defines `TradeRepository` as a `typing.Protocol`. Both
`PostgresTradeRepository` and `InMemoryTradeRepository` satisfy it structurally, with no
inheritance relationship required. This keeps the test double completely independent of the
production implementation - it can't accidentally inherit (and hide bugs in) Postgres-specific
behavior.

## 4. The event bus is in-process, not a message broker
`EventBus` (`atlas/events/bus.py`) is `asyncio`-based pub/sub within the one running process -
no Redis, no persistence, no delivery guarantee across restarts. That's the correct amount of
infrastructure for a single FastAPI instance with no other consumers yet. The interface
(`publish`/`subscribe`) is what matters for the future: if Atlas ever runs multiple instances,
this class is the seam where a real broker replaces it without touching any code that calls
`publish`.

## 5. A genuine hardening found during implementation: the advisory-lock claim
**This is the "challenge the plan" case rule 6 asks for.** The Sprint 0 idempotency guard
(check `pmt_forwarded`, then forward, then store) had a latent concurrency gap: two truly
concurrent webhook deliveries for the same `correlation_id` could both pass the check before
either had written its result, and both could reach PickMyTrade - a duplicate real order.
SQLite's single-writer model made this unlikely in practice, but nothing actually prevented
it, and the original design never claimed to.

Since Postgres was already being introduced this sprint, closing this gap was cheap:
`PostgresTradeRepository.claim_and_forward` wraps the whole check-forward-store sequence in
one transaction holding a `pg_advisory_xact_lock` scoped to the correlation_id. A second
concurrent request for the same id blocks until the first transaction commits, then correctly
sees `pmt_forwarded = true` and is treated as a duplicate. Verified in
`tests/integration/test_postgres_repository.py::test_concurrent_duplicate_webhooks_only_forward_once`
by firing two real concurrent calls at a real Postgres database and asserting the forward
function was called exactly once.

Trade-off accepted: a pooled connection (and the advisory lock) is held for the duration of
the PickMyTrade HTTP call, up to its 15s timeout. Acceptable given this strategy's low signal
frequency and a pool sized for it (`min_size=1, max_size=10`); revisit pool sizing if signal
frequency changes materially.

## 6. Claude runs fully async now, offloaded to a thread
Sprint 0 relied on `BackgroundTasks` running a sync function in a threadpool automatically.
Sprint 1's `run_claude_analysis` is `async def` (so it can `await` the async repository) and
explicitly wraps the blocking `anthropic` SDK call in `asyncio.to_thread`. Net effect is the
same non-blocking guarantee as before, made explicit rather than incidental, and correct for
an async repository that must run on the app's event loop rather than a separate thread's own
loop.

## 7. Migrations run once at startup, not per-request
Sprint 0's `get_conn()` re-ran the entire SQLite schema script on every single webhook/dashboard
request. Sprint 1 runs pending migrations once during the FastAPI `lifespan` startup hook
(`migrations/runner.py`, tracked in a `schema_migrations` table) and then reuses a connection
pool for the life of the process. Faster, and it's what makes the advisory-lock guarantee
correct (the lock needs to be scoped to a real transaction on a pooled connection).

## 8. `/health` now checks the database, not just the process
A process can be "up" with a dead database connection - that's exactly the failure mode
worth surfacing. `/health` now calls `TradeRepository.ping()` and returns 503 if it fails,
matching the "Connection Status" screen concept from the approved V2 frontend design.

## 9. API versioning without breaking the existing webhook
`/webhook` and `/health` are mounted twice: once unversioned (permanent, since TradingView's
existing alert already points at `/webhook` and there's no reason to ever force a
reconfiguration) and once under `/api/v1/` (canonical path for new integrations). Both paths
hit the identical router/handler - there is no behavioral difference, only the URL.

## 10. What was deliberately left alone
Per the sprint's explicit constraints: no strategy logic changes, no parameter tuning, no
Pine changes (no payload-compatibility issue arose), and the dashboard HTML is unchanged
pixel-for-pixel from Sprint 0 - the V2 frontend redesign is out of scope for this sprint.
`received_at`/`signal_time`/`last_update_at`/`closed_at` remain TEXT columns (ISO-8601
strings) rather than `TIMESTAMPTZ`, matching Sprint 0 exactly, to avoid touching dashboard
rendering or test assertions for no behavioral benefit this sprint.

# Phase 18H-1 — Offline AI Persistence Runtime Wiring

Status: local implementation candidate only. Phase 18E remains disabled and no
analysis route, provider call, production database, deployment, retention
worker, backup, or operational enablement is authorized by this phase.

## Composition boundary

`atlas.ai_persistence_runtime` owns the non-frozen application composition for
the certified Phase 18F coordinator and the locally qualified Phase 18G
PostgreSQL adapter. It does not change any Phase 18A–18F contract.

The FastAPI lifespan owns exactly one dedicated synchronous
`psycopg_pool.ConnectionPool` when AI persistence is required. The adapter
receives a bounded `pool.connection()` context factory and continues to own each
logical persistence transaction. The pool is separate from the existing Atlas
application database pool, is closed once on shutdown, and is also closed on a
partial startup failure.

No provider, orchestrator, route, request handler, worker, scheduler,
background task, or call to `PersistenceCoordinator.persist()` is added here.

## Configuration

| Name | Classification | Behavior |
|---|---|---|
| `ATLAS_AI_PERSISTENCE_MODE` | non-secret | Closed to `disabled` or `required`; defaults disabled. |
| `ATLAS_AI_PERSISTENCE_DATABASE_URL` | secret | Dedicated runtime-writer DSN; read only in required mode. Never falls back to `DATABASE_URL`. |
| `ATLAS_AI_PERSISTENCE_CONNECT_TIMEOUT_SECONDS` | bounded tuning | Positive and no greater than 30 seconds. |
| `ATLAS_AI_PERSISTENCE_POOL_MIN_SIZE` | bounded tuning | Integer 1–20 and no greater than maximum. |
| `ATLAS_AI_PERSISTENCE_POOL_MAX_SIZE` | bounded tuning | Integer 1–20. |
| `ATLAS_AI_PERSISTENCE_POOL_ACQUISITION_TIMEOUT_SECONDS` | bounded tuning | Positive and no greater than 30 seconds. |
| `ATLAS_AI_PERSISTENCE_LOCAL_DISPOSABLE_TEST` | local qualification only | Closed boolean. It permits only loopback qualification in `ENVIRONMENT=development` and is invalid with disabled mode. |

Production-style configuration requires a non-local host, complete connection
identity, a credential, and `sslmode=verify-full`. Privileged or obviously
disposable role/database identities fail configuration validation. No hostname,
user, database, password, DSN, or raw parsing/driver exception enters a status
response or startup exception.

Provider-specific production pool sizing and timeout values remain unresolved.

## Startup, schema, and privilege verification

Required-mode startup performs exactly one bounded construction attempt:

1. validate non-secret configuration;
2. validate the secret DSN without rendering it;
3. construct and open the dedicated pool with pool reconnect time disabled;
4. verify the exact code-owned migration filename/checksum map;
5. verify runtime identity and effective privileges using read-only catalog
   functions;
6. construct the Phase 18G adapter and Phase 18F coordinator; and
7. publish the ready runtime on `app.state.ai_persistence_runtime`.

Migration `0002_runtime_schema_verification.sql` grants the writer column-level
`SELECT` only on `filename` and `sha256` in the existing migration ledger. It
grants no ledger mutation or migration authority.

Startup verifies database `CONNECT`, protected-schema `USAGE`, ledger-column
read access, and persistence-table `SELECT`/`INSERT`. It rejects schema `CREATE`,
table `UPDATE`/`DELETE`/`TRUNCATE`, ledger mutation, superuser, database/role
creation, replication, bypass-RLS, database/schema ownership, and membership in
the schema-owner role. Startup never commits a probe record and never runs a
migration.

Failures are closed fixed classifications: `configuration_invalid`,
`schema_mismatch`, `privilege_invalid`, or `unavailable`. No automatic retry or
fallback exists.

## Health and readiness

The existing health response gains one additive `ai_persistence` object with a
fixed `status` and `required` boolean. Supported states are `disabled`,
`starting`, `ready`, `unavailable`, `configuration_invalid`, `schema_mismatch`,
`privilege_invalid`, and `shutdown`.

Disabled persistence does not affect existing health. Required persistence must
be `ready`; otherwise readiness returns HTTP 503 while unrelated application
functionality remains unchanged. Each health request performs one new bounded
read-only observation through `asyncio.to_thread`; it does not retry a store or
generate an analysis. Recovery is reported only by a later independent health
observation.

## Async caller rule

No synchronous store operation is invoked by Phase 18H-1. Any later FastAPI
caller must use a bounded worker-thread boundary, must budget worker concurrency
against the connection-pool maximum, and must not add a retry at the thread,
application, pool, or adapter boundary.

## CI and local qualification

CI uses the official PostgreSQL 17.10 image pinned to the approved immutable
digest and a separate mandatory Phase 18G/18H test command with synthetic
credentials. The command checks that its database variable exists, so the
integration files cannot silently pass through their local skip guard.

Qualification covers disabled configuration, TLS and bounds validation,
single-pool construction, partial-startup cleanup, shutdown idempotency,
schema/checksum verification, narrow ledger access, positive and prohibited
privileges, unavailable/readiness transitions, migration bootstrap and upgrade
surface, existing replay/collision/concurrency/canonical-byte behavior, and the
absence of startup probe records.

## Authorization boundary

Phase 18H-1 grants no production provider selection, PostgreSQL provisioning,
real credential, remote database access, runtime migration, deployment, Phase
18E activation, provider call, analysis API, destructive testing, backup/PITR,
RPO/RTO evidence, retention deletion, legal hold, trading, or operational
authority. These remain separately reviewed stages.

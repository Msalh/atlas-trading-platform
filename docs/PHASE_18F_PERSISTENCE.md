# Phase 18F — Offline Persistence Contract and Atomic Storage Port

Status: offline implementation work package. Independent certification is
required before closure. This document authorizes no concrete storage, runtime
attachment, deployment, or operational enablement.

## Objective and authority

Phase 18F defines a deterministic, technology-neutral boundary for atomically
storing the sanitized typed outcomes of Phase 18D. Phase 18B remains the sole
semantic-validation and audit-construction authority. Phase 18F neither
revalidates provider output nor constructs an AI audit.

Phase 18F is offline-only, default-unattached, and dependent solely on an
injected port. It grants no strategy, risk, decision, trading, broker, order, or
execution authority.

## Non-goals

- PostgreSQL, another database, ORM code, migrations, or storage schemas;
- HTTP, service routes, startup, worker, or dependency-injection composition;
- Railway, provider access, credentials, pricing, or network access;
- retries, fallback, distributed locks, or a production concurrency mechanism;
- retention, deletion, purge, backup, restore, or legal-hold policy;
- deployment, live observability, or operational certification.

The frozen Phase 18A schemas and policy remain unchanged.

## Accepted typed outcomes

| Phase 18D input | Phase 18F behavior |
|---|---|
| `CompletedOutcome` | Construct one closed record from the retained exact `ValidatedAnalysisOutput` and matching Phase 18B completed audit; invoke storage once. |
| `FailedOutcome` | Construct an audit-only record after checking failed outcome and reason consistency; invoke storage once. |
| `RefusedOutcome` | Construct an audit-only record after checking refused outcome consistency; invoke storage once. |
| `ServiceUnavailableOutcome` | Return a fixed ephemeral not-persistable result, construct no record or audit, and make zero port calls. |

Raw mappings, provider candidates, prompts, evidence, responses, credentials,
headers, diagnostics, and arbitrary caller objects are not accepted.

## Trusted validated-output provenance

`CompletedOutcome` retains the exact capability-protected
`ValidatedAnalysisOutput` returned by Phase 18B while preserving the existing
immutable public `output` view. Its supported constructor is closed. Phase 18F
requires that retained object and never reconstructs trust from a mapping or
calls `validate_output()` again.

The persistence DTO constructors are also closed. This is an application
authority boundary and, like the Phase 18B capability, is not a claim of
protection against hostile same-process reflection into private Python members.

## Immutable persistence DTOs

`CompletedPersistenceRecord` contains the trusted validated output, its matching
completed audit, canonical bytes, SHA-256 digests, audit operation identity, and
output identity. `AuditOnlyPersistenceRecord` contains only the failed or refused
audit, its canonical bytes and digest, operation identity, and outcome category.

Canonical representations use the established Phase 18B canonical JSON and audit
serialization functions. These DTOs are internal port values, not new wire
schemas.

## Identity and integrity invariants

Before invoking storage, completed output and audit must agree exactly on:

- analysis input and output identities;
- Snapshot identity and evidence digest;
- purpose;
- frozen input, output, and policy contract versions;
- completed/available outcome status; and
- the provider and exact model identity retained by Phase 18D.

Phase 18F does not rewrite or normalize any identity. Failed and refused audits
must have a null output identity, the expected audit outcome, and a reason
consistent with the typed Phase 18D outcome. Any violation fails before storage.

## Atomic port and coordinator contract

`AtomicPersistencePort.store_atomic()` is one logical operation. A completed
record commits output and audit together or exposes neither. An audit-only record
commits its audit or exposes nothing. A successful immutable receipt means the
whole logical record committed or was an exact replay.

The coordinator invokes the port at most once. It contains no retry and never
reports partial or uncertain success. Storage-specific transaction and locking
details do not enter the public contract.

## Replay, collision, and concurrency

- The frozen audit ID is the operation identity.
- The output ID is additionally unique for a completed record.
- Byte-identical replay of an operation returns an equivalent replay receipt and
  creates no duplicate.
- Reuse of an audit ID with different canonical content is a conflict.
- Reuse of an output ID with different output, audit, or binding is a conflict.
- Concurrent identical submissions yield one logical record and equivalent
  committed/replayed receipts.
- Concurrent conflicts permit at most one commit; losers receive a sanitized
  conflict failure.

These are adapter obligations. Phase 18F implements no production lock manager.

## Partial failure and rollback

Failure before a write, between logical writes, during commit, on timeout or
cancellation, or while attempting rollback must leave no partially visible
output or audit. If commit or rollback state is uncertain, the operation fails
closed and must not return success. No automatic retry is permitted.

## Sanitized failures and results

The fixed failure classes are `PersistenceUnavailableError`,
`PersistenceTimeoutError`, `PersistenceConflictError`, and
`PersistenceIntegrityError`. They contain only their generic classification.
Adapter messages, backend identities, SQL, objects, transaction details, record
content, prompts, evidence, provider payloads, credentials, causes, contexts,
and tracebacks do not cross the boundary.

Results contain only a committed/replayed operation receipt or the fixed
pre-eligibility not-persistable classification.

## Pre-eligibility service failure

The frozen `ai_analysis_audit.v1` schema cannot represent Phase 18C
`ServiceFailure`. Phase 18F therefore does not persist the resulting
`ServiceUnavailableOutcome` and does not fabricate an audit, input ID, output ID,
digest, or refusal reason. A future operational-event contract or frozen schema
version requires separate authorization.

## Retention and deletion

Retention duration, deletion and purge authority, legal holds, data residency,
backup, restore, and encryption/key ownership are **REQUIRES HUMAN INPUT**. No
default is inferred and no such behavior is implemented in Phase 18F.

## Offline acceptance matrix

Permanent deterministic tests must cover trusted completed provenance;
completed atomic success; failed/refused audit-only success; zero-call service
unavailability; raw and forged input rejection; every identity, digest, contract,
outcome, reason, provider, and model mismatch; exact replay; audit/output identity
collision; identical and conflicting concurrency; every partial-write, commit,
timeout, cancellation, and rollback failure; zero partial visibility; immutable
records and receipts; one-call/no-retry behavior; hostile cause/context redaction;
and static absence of concrete storage, HTTP, Railway, provider, broker,
deployment, runtime bindings, and production-reachable test fakes.

All qualification uses deterministic in-memory test fakes. The fake is test-only
and cannot be imported by production construction or runtime code.

## Independent certification and later boundaries

Phase 18F is complete only after focused tests, the combined Phase 18A–18F and
Snapshot regressions, Ruff/static checks, whitespace and credential scans,
authority/dependency scans, full diff review, and an independent read-only
certification pass.

Concrete storage, migrations, retention/deletion, API/service integration,
runtime attachment, deployment/observability, and operational certification are
later, separately approved boundaries. Phase 18E operational blockers remain
closed and are not changed by Phase 18F.

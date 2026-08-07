# Phase 18G — Concrete PostgreSQL Persistence Adapter Architecture

Status: the narrow PostgreSQL adapter, schema, and migration implementation is a
locally qualified candidate. Qualification used only the disposable container
defined in this repository. No production database, retention process, backup,
runtime attachment, deployment, or operational certification exists by virtue
of this implementation.

## Objective

Define the implementation-ready architecture and future qualification plan for a
PostgreSQL adapter implementing the certified Phase 18F atomic storage port. This
document is a specification and decision record, not adapter code, SQL, a
migration, a provisioned database, or an operational attachment.

## Approved product decisions

The following decisions are approved:

1. Use a dedicated, isolated PostgreSQL database for AI-analysis persistence. Do
   not reuse an application database or a shared schema.
2. Retain every committed completed, failed, and refused persistence record for
   12 months from its authoritative audit `recorded_at` timestamp. At the
   boundary, records become eligible for controlled deletion; approval of a
   deletion mechanism remains separate.
3. Design recovery controls for an RPO of no more than one hour and an RTO of no
   more than four hours.
4. Separate migration and runtime roles. Runtime authority excludes schema
   modification.
5. Require encrypted connections, private networking, and environment isolation.

These decisions do not approve a PostgreSQL version, hosting provider, region,
schema, migration framework, credential, retention worker, backup configuration,
or production target.

## Certified inputs and preserved authorities

- Phase 18A frozen schemas remain unchanged.
- Phase 18B remains the sole semantic-validation and audit-building authority.
- Phase 18C evidence authority and Phase 18D orchestration behavior remain intact.
- Phase 18E remains default-disabled, unattached, and operationally blocked.
- Phase 18F supplies the technology-neutral records, receipts, errors,
  idempotency/collision rules, atomicity boundary, and sanitized failure contract.
- Phase 18F grants no runtime, storage, trading, broker, order, or execution authority.
- The operational pricing catalog remains empty.

## Explicit non-goals

- selecting a database, service, ORM, driver, or migration framework;
- writing production or test code, schemas, migrations, or adapters;
- provisioning, connecting to, inspecting, or mutating storage;
- implementing retention, deletion, purge, legal hold, backup, or restore;
- API, scheduler, worker, dependency-injection, or runtime wiring;
- provider enablement, credentials, deployment, Railway work, or certification;
- changing a frozen schema or duplicating Phase 18B validation; and
- trading, broker, alert, decision, risk, or execution integration.

## Required storage invariants

The future design must preserve these Phase 18F requirements:

1. A completed output and its matching audit become visible atomically or neither does.
2. Failed and refused outcomes store exactly one audit-only record atomically.
3. Pre-eligibility service failures make no storage call and fabricate no record.
4. Exact replay returns the original immutable receipt without another write.
5. Identity, digest, outcome, provider, model, audit-ID, or output-ID conflicts
   fail closed and never overwrite committed state.
6. Concurrent identical and conflicting requests have deterministic outcomes.
7. Staged or rolled-back state is never externally visible as committed state.
8. Timeout, cancellation, uncertain commit, and rollback failure remain explicit,
   sanitized boundaries; silence cannot imply success.
9. The adapter stores exact trusted values without normalization, coercion,
   repair, reconstruction, or semantic revalidation.
10. A success receipt is issued only after the approved durability boundary.

## PostgreSQL selection and remaining decision criteria

PostgreSQL in a dedicated isolated database is the approved default technology
and topology. Provider and version selection remain unresolved. Candidate
deployments must be compared on:

- native transaction and constraint capabilities for the complete atomic unit;
- isolation, locking, concurrency, and deterministic conflict behavior;
- durability acknowledgements and documented crash-recovery semantics;
- exact-value and canonical-byte preservation where physically required;
- enforceable uniqueness and referential-integrity constraints;
- migration safety, rollback strategy, compatibility windows, and tooling;
- backup, point-in-time recovery, restore rehearsal, and RTO/RPO support;
- least-privilege credentials, encryption, key ownership, and rotation;
- sanitized observability without record, credential, or diagnostic leakage;
- retention/deletion and legal-hold capabilities; and
- operational complexity, portability, supportability, and cost.

## Transaction, replay, locking, durability, and rollback questions

The design and its independent review must approve:

- the transaction boundary for completed pairs and audit-only records;
- physical uniqueness keys for replay and collision enforcement;
- isolation level, lock acquisition order, and concurrent-writer behavior;
- the durability acknowledgement required before returning success;
- timeout and cancellation behavior before, during, and after commit;
- recovery from uncertain commit without an unsafe blind retry;
- sanitized distinction between rollback success and rollback failure;
- whether any scheduler or worker exists and its separate authority;
- mixed-version migration compatibility and rollback; and
- recovery proof that no partial pair becomes visible.

## Schema and migration decisions requiring human approval

- PostgreSQL version, provider, region, database owner, and operational owner;
- representation of outputs, audits, receipts, identities, and canonical encoding;
- fields, indexes, constraints, and referential integrity;
- migration framework, version authority, compatibility window, and rollback policy;
- isolation level, lock strategy, transaction timeout, and connection policy;
- durability setting and success-acknowledgement boundary; and
- disposable qualification environment and its data lifecycle.

No default may be inferred for any item above.

## Retention and deletion architecture

The approved retention period is 12 months for completed, failed, and refused
records. The period starts at the frozen audit `recorded_at` timestamp because it
is present in every persisted audit and represents the authoritative audit event
time. A separate database commit timestamp may be retained for operations but
must not reset or replace the retention clock.

Future controlled deletion must use bounded batches, short transactions,
throttling, an indexed retention timestamp, deterministic high-water marks, and
sanitized aggregate evidence. A failed batch may be retried only by the future
retention mechanism under its separately approved idempotency contract. It must
not broaden the Phase 18F coordinator's no-retry boundary.

Exact replay after approved deletion is no longer a database replay: it is a new
commit unless a separately approved deletion ledger or tombstone policy says
otherwise. No tombstone is approved here. This consequence must be accepted or a
minimal non-sensitive replay tombstone must receive separate approval before
retention implementation.

Legal hold, incident preservation, purge authority, backup expiration, data
residency, encryption-key ownership, and privacy/export obligations remain
unresolved. A record subject to an approved investigation hold must not be
deleted, but no hold model is authorized until governance supplies one.

## Logical PostgreSQL model

Use one immutable persistence-record table capable of representing both a
completed output/audit pair and an audit-only failed or refused outcome. A single
row is the narrowest model because it makes the Phase 18F logical atomic unit the
physical visibility unit, supports audit-only records without placeholder output
rows, and avoids cross-table partial-state and recovery complexity.

### Contract-required fields

- audit/operation identity as the primary identity;
- nullable output identity, unique when present;
- outcome classification: completed, failed, or refused;
- authoritative canonical audit bytes and supplied audit digest;
- nullable authoritative canonical output bytes and supplied output digest;
- analysis-input, snapshot, purpose, evidence-digest, contract-version,
  provider, and exact-model projections required to enforce Phase 18F bindings;
- audit `recorded_at`, which is also the approved retention timestamp; and
- a physical persistence-schema version.

### Operationally useful fields

- database commit timestamp for operations and recovery evidence, never as a
  replacement for `recorded_at`;
- fixed deletion-eligibility timestamp derived from `recorded_at` plus 12 months;
  the exact calendar arithmetic must be approved and tested before migration;
- sanitized migration version and, if approved, a non-secret operational
  correlation identifier.

### Prohibited fields

- raw prompts or evidence content;
- provider requests, responses, or transport diagnostics;
- credentials, authorization headers, endpoints, or secrets;
- raw exception text, SQL, or backend identifiers;
- unnecessary personal, user, tenant, or application data; and
- a duplicate parsed payload treated as authoritative.

Tenant identity, legal-hold state, deletion tombstones, export state, and
provider-specific recovery metadata remain unresolved. They must not be silently
added during implementation.

## Canonical representation and integrity

Store the exact Phase 18F canonical audit and output bytes in binary columns.
Those bytes are authoritative. PostgreSQL `jsonb` normalization must never
replace them. Parsed JSON projections are unnecessary for the initial model;
future non-authoritative projections require a documented query purpose and
readback consistency checks.

Store the Phase 18F supplied SHA-256 digests unchanged, together with frozen
contract versions and the physical persistence-schema version. The adapter must
recompute each digest and compare it with the supplied digest before writing as a
defensive integrity check. A successful comparison does not recreate Phase 18B
trust, authorize an untrusted mapping, or replace the closed Phase 18F DTO.
Mismatch maps to sanitized `persistence_integrity` before any write.

Historical readers must dispatch by retained versions and fail closed on an
unsupported version. They must not silently reserialize historical bytes under a
new canonicalization implementation.

## Constraints, indexes, and immutability

The future schema must provide:

- primary uniqueness for audit/operation identity;
- partial uniqueness for non-null output identity;
- closed outcome-classification checks;
- completed-shape checks requiring output identity/bytes/digest and applicable
  provider/model and input bindings;
- audit-only checks requiring null output identity/bytes/digest;
- non-empty canonical bytes and lower-case SHA-256 format checks;
- exact frozen contract-version checks or an explicitly versioned compatibility
  mechanism; and
- runtime denial of UPDATE, DELETE, TRUNCATE, DDL, ownership, role management,
  and trigger administration.

Indexes are limited initially to the primary audit identity, unique output
identity, and the approved retention/deletion eligibility order. Additional
snapshot, input, digest, provider, or model indexes require an approved access or
operational purpose.

Immutability is enforced primarily by privileges and insert-only adapter code. A
defensive update-rejection trigger is recommended but remains an implementation
choice because it adds function ownership and migration surface requiring its own
qualification.

## Transaction, isolation, replay, and collision

Use one explicit PostgreSQL transaction at `READ COMMITTED`, one complete row,
and database unique constraints. This is the smallest defensible strategy;
`REPEATABLE READ`, `SERIALIZABLE`, advisory locks, and explicit row locks add
failure and retry behavior not required by the single-row design.

The adapter performs one insert attempt. On success it commits and returns
`committed` only after the approved durability acknowledgement. On a uniqueness
conflict it reads the committed row by audit identity and, when relevant, output
identity, then compares the complete canonical replay fingerprint. Byte-identical
records return `replayed`; any different identity, bytes, digest, classification,
or binding returns sanitized `persistence_conflict`.

Concurrent identical first writers must yield one commit and equivalent replay
receipts. Concurrent conflicting writers permit at most one commit. Constraint
losers return conflict after comparing the committed winner. No staged row is
externally visible.

Deadlock, serialization, timeout, cancellation, connection loss, rollback
failure, and lost commit acknowledgement fail closed. The adapter and driver may
not automatically replay the transaction. A driver-level transaction retry is a
second logical persistence attempt and is prohibited unless a later contract
explicitly proves it equivalent. After acknowledgement loss, a later independent
submission may resolve through exact replay; the original call must not claim
success.

## Recovery architecture

RPO no greater than one hour requires recoverable backup or log-archive points at
least hourly. Continuous write-ahead-log archiving with verified base backups is
recommended when supported; otherwise the selected provider must prove that its
native backup interval and recovery semantics meet the same bound.

RTO no greater than four hours requires a documented, rehearsed restore into an
isolated environment, including database provisioning, backup selection,
restore, migration compatibility, integrity verification, sanitized aggregate
record counts, application-readiness checks, and operator handoff within four
hours.

Backups must be encrypted, access-separated from runtime and migration roles,
regionally compliant, and retained consistently with the 12-month lifecycle.
Expired source records must not remain indefinitely recoverable through backups;
the exact backup-retention overlap and purge semantics require explicit policy.
Provider-specific PITR granularity, backup immutability, restoration time,
encryption, regional placement, and cost must be independently verified later.

Restore testing is required initially and periodically at a frequency still
requiring Operations approval. A restore cannot target or replace production
during qualification.

## Least-privilege role model

- A NOLOGIN schema-owner template owns the schema and objects.
- A separately controlled migration identity may assume schema-owner authority
  only during an approved migration.
- The runtime role receives CONNECT, schema USAGE, INSERT, and narrowly necessary
  SELECT for replay/collision resolution. It receives no DDL, UPDATE, DELETE,
  TRUNCATE, ownership, role-management, trigger, or administrative privilege.
- An optional operational reader receives CONNECT, schema USAGE, and SELECT only
  after a separately approved purpose and evidence boundary.
- Backup/restore authority belongs to a separate platform role or the selected
  managed provider and is never inherited by runtime.

All environments use separate credentials and isolated databases. Connections
must be encrypted and privately networked. Credential ownership, distribution,
rotation, access logging, and operator access require Security/Operations
approval. Logs contain only fixed classifications and sanitized aggregate
metadata; canonical payloads, digests, identifiers where unnecessary, connection
properties, and diagnostics are excluded.

## Migration architecture

Use version-controlled, checksum-bound migrations owned by the migration role.
The repository already demonstrates reviewed plain SQL migrations, but this does
not select a framework for Phase 18G. Framework choice remains open pending a
comparison of checksum enforcement, transactional DDL, locking, drift detection,
and dependency policy.

Bootstrap must work deterministically on an empty database. Every non-empty
upgrade must define the supported prior version, mixed-version compatibility
window, lock duration, failure behavior, evidence, and rollback limitation.
Prefer roll-forward after data-bearing changes; permit downgrade only when proven
lossless. Qualify transactional DDL where PostgreSQL supports it and explicitly
handle non-transactional operations. Production migration remains a separate
authorization.

## Disposable qualification environment

Future implementation requires exactly one approved disposable PostgreSQL target
with a pinned major and minor version, private networking, isolated credentials,
deterministic bootstrap, and no production data or service binding. Parallel
tests use separate databases or schemas with unique identities; clean reset must
be deterministic and target-only.

Ordinary integration qualification covers bootstrap, constraints, privileges,
completed/audit-only commits, replay, collisions, visibility, concurrent writers,
migration upgrades, retention eligibility, bounded deletion, and sanitized error
translation.

Separate infrastructure authorization is required for process termination,
network interruption, lost-acknowledgement simulation, rollback failure,
crash/restart durability, deadlock stress, backup creation, isolated restore,
RPO/RTO measurement, and target cleanup. Evidence is limited to versions,
migration checksums, aggregate counts, generic classifications, timestamps, and
sanitized target identity.

## Remaining decision register

| Decision | Logical implementation | Disposable certification | Production deployment | Operational enablement |
|---|---|---|---|---|
| PostgreSQL version and provider | Blocks dependency/SQL finalization | Blocks | Blocks | Blocks |
| Disposable qualification target | Does not block local unit design | Blocks | Does not by itself block | Does not by itself block |
| Geographic residency | Does not block DTO/adapter skeleton | May block target approval | Blocks | Blocks |
| Encryption-key ownership/rotation | Does not block offline adapter | Partly blocks security proof | Blocks | Blocks |
| Tenant/user isolation requirement | Blocks final schema | Blocks | Blocks | Blocks |
| Legal hold | Does not block core insert path; blocks deletion model | Blocks retention certification | Blocks retention enablement | Blocks deletion operations |
| Privacy/export obligations | May block schema and read surfaces | May block | Blocks | Blocks |
| Support/operator access | Does not block core adapter | Partly blocks role proof | Blocks | Blocks |
| Backup retention and expiry overlap | Does not block insert path | Blocks recovery certification | Blocks | Blocks |
| Backup provider/topology | Does not block insert path | Blocks RPO/RTO proof | Blocks | Blocks |
| Database owner and on-call owner | Does not block offline code | Blocks operational evidence | Blocks | Blocks |
| Production target | Does not block disposable implementation | Does not block disposable tests | Blocks | Blocks |

No legal or business requirement is inferred from this register.

## Failure, recovery, and security boundaries

- Credentials, connection properties, record contents, and raw driver diagnostics
  must not enter tests, evidence, exceptions, or logs.
- The future adapter must translate failures into the bounded Phase 18F sanitized
  vocabulary without retaining cause or context.
- Administrative, migration, runtime-writer, read-only verifier, backup, and
  restore authorities must be separated and least-privileged.
- Uncertain-commit recovery must use an approved identity/replay lookup and must
  not perform an automatic duplicate write.
- Migration, backup/restore, retention/deletion, and operational rollback each
  require separate approvals and evidence plans.

## Future tests and independent certification gates

Implementation, if later authorized, must first qualify against a disposable,
isolated target and include:

- every Phase 18F conformance and adversarial case;
- atomic pair and audit-only commit visibility;
- exact replay and every identity/collision variant;
- concurrent identical and conflicting writers;
- between-write, pre-commit, commit, timeout, cancellation, disconnect, crash,
  rollback-success, and rollback-failure injection;
- durability and restart/recovery evidence at the approved acknowledgement boundary;
- migration forward/compatibility/rollback evidence under the approved policy;
- privilege, credential, redaction, dependency, and runtime-isolation scans;
- backup/restore evidence only under a separate operational approval; and
- full Phase 18A–18F and Snapshot regressions plus independent read-only review.

The in-memory Phase 18F suite cannot certify a concrete adapter's transactions,
durability, locking, migration, or recovery behavior.

## Architecture and implementation gates

Architecture closure requires the certified Phase 18F commit, this PostgreSQL
decision package, and independent documentation review. Later implementation
also requires approval of the blocking items in the decision register, a pinned
PostgreSQL version and driver, a reviewed schema and migrations, a disposable
target, and an exact fault-injection and evidence plan.

Architecture closure grants no implementation or operational authority.

## Future narrow implementation authorization

A later approval may authorize only:

- one concrete PostgreSQL implementation of `AtomicPersistencePort`;
- one reviewed physical schema and version-controlled migration set;
- adapter unit tests and integration tests against one isolated disposable target;
- the approved canonical-byte, constraint, transaction, replay, collision,
  concurrency, privilege, and sanitization behavior; and
- retention eligibility and deletion code only if separately and explicitly
  authorized after legal-hold and deletion-governance decisions close.

That approval must exclude production databases, production credentials,
API/runtime attachment, startup or worker binding, Phase 18E provider enablement,
deployment, and operational certification.

Implementation prerequisites are: resolved tenancy, residency, legal-hold and
privacy impacts on the schema; approved PostgreSQL version/provider for the
disposable target; approved driver/dependency pin; schema and migration review;
key/credential ownership; disposable-target authorization; and reviewed
qualification, failure-injection, cleanup, and redaction procedures.

## Recommended dependency order

1. Resolve data classification, residency, encryption, legal hold, tenancy,
   privacy/export, backup retention, and operator ownership.
2. Select and pin the PostgreSQL version, provider for the disposable target,
   driver, and operational owner.
3. Approve schema, constraints, migrations, transaction/isolation/locking rules,
   durability boundary, compatibility, and rollback plan.
4. Separately authorize implementation against an isolated disposable target.
5. Independently certify adapter-specific atomicity, durability, concurrency,
   migration, failure, and recovery behavior.
6. Define and review API/runtime authorization, idempotency, and wiring separately.
7. Close Phase 18E model, account, retention/ZDR, pricing, secret-ownership, and
   runtime-factory gates before live provider enablement. These may proceed in
   parallel but cannot weaken persistence gates.
8. Separately authorize deployment, sanitized observability, rollback rehearsal,
   and operational certification.

## Local implementation and ordinary qualification record

The narrow implementation authorization selected PostgreSQL 17.10 and the
official Linux image
`postgres@sha256:7958605b474b3d264a969cb3a123d6aa00ad1e1fe9da8a69984dabb704d93317`.
The repository-compatible dependency pins are `psycopg[binary,pool]==3.3.4`
and `psycopg-pool==3.3.1`; their published metadata supports Python 3.12.

The implementation is isolated in `atlas_ai_persistence_postgres` and
`ai_persistence_migrations`. It provides one synchronous, insert-only
`AtomicPersistencePort` adapter, one checksum-bound migration runner, and one
physical persistence-record table. The adapter uses one explicit
`READ COMMITTED` transaction and one insert attempt. Exact replay reads and
compares the complete trusted fingerprint; conflicts fail closed. It performs
no retry, persistence semantic validation, runtime registration, provider call,
or retention deletion.

### Trusted-record to physical-field mapping

| Trusted source | Physical field | Authority and constraint |
|---|---|---|
| audit operation ID | `analysis_audit_id` | Primary identity; exact UUID |
| completed output ID | `analysis_output_id` | Nullable; unique when present |
| audit outcome | `outcome` | Closed to completed, failed, or refused |
| audit input/snapshot identities | `analysis_input_id`, `snapshot_id` | Exact trusted identities; completed input required |
| audit evidence/purpose | `evidence_digest`, `purpose` | Exact trusted projections |
| frozen contract versions | three contract-version columns | Exact frozen version checks |
| trusted generator identity | `provider_id`, `model_id` | Required only for completed records |
| audit event time | `audit_recorded_at` | Authoritative retention clock; no deletion authority |
| exact audit bytes and digest | `audit_payload`, `audit_digest` | Binary bytes retained unchanged; digest compared before connection |
| exact output bytes and digest | `output_payload`, `output_digest` | Nullable audit-only shape; unchanged when completed |
| adapter constants | schema/profile columns | Closed physical schema and canonicalization versions |
| database | `committed_at` | Operational commit time only; never replaces audit time |

The disposable environment is defined by `compose.phase18g.yml`. It is
digest-pinned, publishes PostgreSQL only on loopback, stores database files on
`tmpfs`, uses synthetic qualification-only credentials, and creates no named or
persistent volume. Ordinary qualification covered empty bootstrap, migration
checksum drift, least-privilege runtime access, completed and audit-only commits,
exact replay, identity and payload collision rejection, concurrent writers,
rollback visibility, immutable rows, canonical-byte preservation, and sanitized
failure translation. The complete local backend suite passed with 2,898 tests,
four established skips, and one established framework deprecation warning.

This evidence does not cover process termination, network interruption,
lost-acknowledgement injection, rollback failure, crash/restart durability,
backup/restore, or RPO/RTO measurement. Those destructive and operational gates
remain separately unauthorized. Retention deletion and legal-hold policy also
remain unresolved; no deletion mechanism was implemented.

## Authorization boundary

Human approval is required for every unresolved decision and transition above.
The completed local implementation authorization grants no production database
access, retention execution, backup/restore, runtime attachment, deployment, or
operational action.

Concrete adapter implementation, adapter certification, runtime dependency
injection, API exposure, Phase 18E activation, deployment, and operational
certification are separate ordered gates. Passing one does not authorize the
next. Nothing in Phase 18G grants provider, trading, broker, order, decision, or
execution authority.

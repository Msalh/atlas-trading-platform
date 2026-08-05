# Proposed Phase 18G — Concrete Persistence Adapter Design and Qualification Specification

Status: roadmap proposal for a design-only work package. Implementation is not
authorized. No phase after Phase 18F was previously named by the authoritative
roadmap.

## Objective

Define the reviewed architecture, human decisions, and future qualification plan
for exactly one concrete persistence adapter implementing the certified Phase 18F
atomic storage port. The result would be a specification and decision record, not
adapter code, a storage schema, a migration, or an operational attachment.

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

## Candidate adapter decision criteria

No candidate is approved. A later human decision must compare candidates on:

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

- concrete storage technology, topology, and service owner;
- representation of outputs, audits, receipts, identities, and canonical encoding;
- fields, indexes, constraints, and referential integrity;
- migration framework, version authority, compatibility window, and rollback policy;
- isolation level, lock strategy, transaction timeout, and connection policy;
- durability setting and success-acknowledgement boundary; and
- disposable qualification environment and its data lifecycle.

No default may be inferred for any item above.

## Retention and deletion decisions requiring human approval

Retention duration, deletion and purge authority, legal holds, data residency,
encryption and key ownership, backup retention, restore authority, RPO, RTO, and
audit-evidence retention are unresolved. They must precede final schema approval
because they may affect layout, indexes, partitioning, keys, and recovery.

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

## Proposed entry and exit gates

Entry to design requires the certified Phase 18F commit, a clean repository base,
and explicit documentation/architecture authorization. Later implementation also
requires approved technology, schema, migration, retention/deletion, security,
durability, and qualification decisions.

The design phase exits only when all decisions are recorded, the adapter and
schema specification is independently reviewed, the qualification and rollback
plans are executable, and a separate implementation approval boundary is written.
Exit grants no implementation or operational authority.

## Recommended dependency order

1. Approve data classification, retention/deletion, residency, encryption, RPO,
   RTO, backup, restore, and legal-hold policy.
2. Select the concrete adapter technology and operational owner.
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

## Authorization boundary

Human approval is required for every decision and transition above. This proposal
authorizes no implementation, test environment, infrastructure access, credential
use, migration, runtime attachment, deployment, or operational action.

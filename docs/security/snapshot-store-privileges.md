# Snapshot Store Migration and Privilege Contract

Phase 17C owns the isolated `atlas_snapshot` PostgreSQL schema. It does not alter
TraderNow, market-data tables, application tables, or production data.

## Authoritative storage

`atlas_snapshot.snapshots.canonical_payload BYTEA` is the sole authoritative
snapshot representation. There is no JSON or JSONB copy. Scalar columns are
derived indexes and are verified against the canonical payload after retrieval.

## Roles

The migration creates four `NOLOGIN NOINHERIT` privilege templates. Credentials
and login roles are provisioned outside the migration.

| Role | Schema | Table privileges | Purpose |
|---|---|---|---|
| `atlas_snapshot_writer` | `USAGE` | `SELECT`, `INSERT` | Runtime append and required conflict reads |
| `atlas_snapshot_reader` | `USAGE` | `SELECT` | Runtime retrieval only |
| `atlas_snapshot_retention` | `USAGE` | `SELECT`, `DELETE` | Separately authorized retention |
| `atlas_snapshot_admin` | owner | schema administration | Migrations only; unavailable to runtime |

`PUBLIC` receives no schema, table, or function privileges. Runtime roles receive
no `CREATE`, `UPDATE`, `DELETE` (writer/reader), `TRUNCATE`, trigger, or schema
administration rights. No sequence exists.

Deployment-specific login roles should be `NOINHERIT`, receive only membership in
one template, and explicitly `SET ROLE` through controlled connection setup. They
must not receive ownership, superuser, database creation, role creation,
replication, or row-security bypass privileges.

## Immutability

All `UPDATE` operations are rejected by a table trigger, including administrative
updates. Corrections insert a new snapshot with `supersedes_snapshot_id`.
Retention deletion is possible only through the separately held retention role;
foreign-key `RESTRICT` prevents deleting evidence still referenced by a
superseding snapshot.

The repository never repairs a digest or metadata value. Invalid canonical bytes,
digest mismatch, unsupported schema, or derived-metadata mismatch raises a typed
corruption error and prevents the row from being returned as usable evidence.
Quarantine is therefore fail-closed and does not mutate the immutable record.

## Migration and rollback

`snapshot_migrations.runner.run_snapshot_migrations()` uses a dedicated
administrative connection and records applied filenames in
`public.atlas_snapshot_schema_migrations`. Runtime services must never receive
that connection.

Before production capture exists, rollback is:

1. revoke memberships from any disposable login roles;
2. drop the empty `atlas_snapshot` schema with the administrative connection;
3. drop the four template roles only after confirming no other database uses
   them;
4. remove the snapshot migration ledger if the database is dedicated.

Once immutable evidence exists, rollback stops runtime access but preserves the
schema until the approved retention process authorizes deletion.

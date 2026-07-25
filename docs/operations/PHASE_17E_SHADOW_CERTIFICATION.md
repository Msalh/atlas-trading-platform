# Phase 17E Private Snapshot Certification

This runbook is an operational procedure, not an architecture contract. Phase
17A–17D contracts remain authoritative. It does not authorize provisioning,
deployment, capture, or Phase 17F.

## Hard gates

Stop immediately when a mandatory item fails. Production shadow capture is
prohibited until isolated smoke, restart, backup/restore, rollback, privilege,
and evidence reviews all pass. Capture is disabled by default and after every
bounded capture window.

Before starting, record:

- approved Phase 17 release commit;
- Railway project, environment, database, and private API service IDs;
- TraderNow deployment revision, health, availability, and baseline latency;
- operator name and UTC certification window;
- empty evidence directory described below.

Do not proceed from a dirty checkout or an unreviewed deployment archive.

## Certification evidence

Store sanitized evidence under:

```text
artifacts/phase-17e-certification/<UTC-date>/
```

Use these files:

```text
00-manifest.md
01-infrastructure.json
02-migration.txt
03-privileges.txt
04-private-smoke.jsonl
05-restart.txt
06-backup-manifest.txt
07-restore-manifest.txt
08-rollback.txt
09-shadow.jsonl
10-trader-now-comparison.txt
11-cleanup.txt
```

Record commands in sanitized form, UTC timestamps, status codes, correlation
IDs, service/deployment IDs, snapshot IDs, evidence digests, row counts, and
measured durations. Never record tokens, passwords, DSNs, private connection
strings, raw infrastructure exceptions, or environment-variable values.

`artifacts/` is excluded from Railway packaging and is not committed with
application source. Certification evidence receives its own approved retention
location and access policy.

## 1. Isolated PostgreSQL

1. Create exactly one isolated PostgreSQL service. Do not reuse the TraderNow
   or any other production database.
2. Verify service health, persistent storage, private DNS, database name,
   PostgreSQL version, and absence of application/public domains.
3. Create two distinct high-entropy passwords outside shell history and two
   login roles using an administrative session:

   ```sql
   CREATE ROLE snapshot_runtime_writer LOGIN NOINHERIT
       NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
       PASSWORD '<generated-secret>';
   CREATE ROLE snapshot_runtime_reader LOGIN NOINHERIT
       NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
       PASSWORD '<different-generated-secret>';
   ```

   Use deployment-scoped role names if multiple certifications share a server.
   Do not put literal credentials in evidence or committed files.

4. From a private, ephemeral maintenance process with administrative
   credentials unavailable to runtime services, execute:

   ```python
   from snapshot_migrations import run_snapshot_migrations
   run_snapshot_migrations("<administrative database URL>")
   ```

5. Run the same migration call again. Verify exactly
   `0001_snapshot_store.sql` appears once in
   `public.atlas_snapshot_schema_migrations`.
6. Grant only template membership:

   ```sql
   GRANT atlas_snapshot_writer TO snapshot_runtime_writer;
   GRANT atlas_snapshot_reader TO snapshot_runtime_reader;
   ```

7. Build writer and reader DSNs that authenticate as their respective login
   roles and select only their template through controlled connection option:

   ```text
   options=-c role=atlas_snapshot_writer
   options=-c role=atlas_snapshot_reader
   ```

8. Using each runtime DSN—not the administrator—record:

   ```sql
   SELECT current_user, session_user;
   SELECT
       has_schema_privilege(current_user, 'atlas_snapshot', 'USAGE'),
       has_schema_privilege(current_user, 'atlas_snapshot', 'CREATE'),
       has_table_privilege(
           current_user, 'atlas_snapshot.snapshots', 'SELECT'
       ),
       has_table_privilege(
           current_user, 'atlas_snapshot.snapshots', 'INSERT'
       ),
       has_table_privilege(
           current_user, 'atlas_snapshot.snapshots', 'UPDATE'
       ),
       has_table_privilege(
           current_user, 'atlas_snapshot.snapshots', 'DELETE'
       ),
       has_table_privilege(
           current_user, 'atlas_snapshot.snapshots', 'TRUNCATE'
       );
   ```

9. Verify writer is `SELECT`/`INSERT` only and reader is `SELECT` only.
   Explicitly prove both reject schema creation, table alteration, update,
   delete, and truncate. Prove the reader rejects insert. Verify neither login
   is superuser, inheriting, role-creating, database-creating, replicating, or
   bypassing row security.
10. Remove the administrative DSN from the maintenance process. It must never
    be configured on the private API.

Migration rollback before evidence exists may drop the empty schema and ledger
with separate administrative authority. Once any snapshot exists, application
rollback preserves the schema and every snapshot. Migration rollback never
updates or deletes evidence.

## 2. Secrets and private API deployment

1. Generate independent reader and operator API tokens with a cryptographically
   secure generator using at least 32 random bytes.
2. Configure the seven variables exactly as documented in
   `SNAPSHOT_PRIVATE_API_DEPLOYMENT.md`. Set
   `SNAPSHOT_CAPTURE_ENABLED=false`.
3. Configure `live/` as source root and set the exact start command:

   ```text
   uvicorn atlas_snapshot_api.runtime:app --host 0.0.0.0 --port $PORT
   ```

4. Deploy the approved commit to one replica with no public or custom domain,
   scheduler, cron, worker, or AI configuration.
5. Confirm the deployed source revision and command. Confirm packaging omitted
   tests, `.tmp`, caches, bytecode, logs, and deployment artifacts.
6. Confirm `GET /health` returns `200`.
7. Confirm authenticated `GET /readiness` returns
   `503 service_disabled`. This is the **expected safe state** while capture is
   disabled; it is not a failed deployment.

## 3. Isolated private smoke

1. Verify every snapshot route returns `401` without credentials.
2. Verify the reader token returns `403` from capture.
3. Verify reader and operator tokens can use read routes.
4. Set `SNAPSHOT_CAPTURE_ENABLED=true` and restart only the private API if the
   platform requires it. Record the resulting deployment/restart.
5. Confirm authenticated readiness returns `200`.
6. Capture the exact approved identity:

   ```json
   {
     "symbol": "MNQ",
     "timeframe": "5m",
     "strategy_id": "displacement_volume_context"
   }
   ```

   Supply a controlled valid correlation ID.
7. Verify `201 created`; record snapshot ID, digest, idempotency key,
   correlation ID, and duration.
8. Retrieve the snapshot, metadata, integrity result, and bounded listing using
   the reader token. Verify canonical payload, derived metadata, and digest.
9. Repeat the same capture. Verify `200 duplicate`, the same snapshot ID, and
   unchanged row count.
10. Exercise invalid request, unauthorized, not-found, invalid cursor, and
    bounded rate-limit behavior. Verify every failure is sanitized and carries
    the expected correlation behavior.
11. Restart only the private API. Reverify health, readiness, snapshot
    retrieval, metadata, integrity, row count, and digest.
12. Set capture to `false`. Verify capture returns
    `503 capture_service_disabled` and row count remains unchanged.

## 4. Backup and isolated restore

1. Record source row count and the complete ordered
   `(snapshot_id, evidence_digest)` manifest.
2. From a private ephemeral maintenance process, use administrative credentials
   unavailable to runtime services:

   ```text
   pg_dump --format=custom --no-owner --no-privileges \
     --file=snapshot-store.dump <administrative-database-url>
   ```

   Keep the URL out of logs and evidence. Encrypt the backup at rest and record
   its SHA-256 without publishing its contents.
3. Create a second disposable isolated database or PostgreSQL service. Do not
   restore over the source.
4. Restore:

   ```text
   pg_restore --clean --if-exists --no-owner --no-privileges \
     --dbname=<isolated-restore-admin-url> snapshot-store.dump
   ```

5. Create disposable reader credentials on the restore target, grant only the
   reader template, and verify read-only privileges.
6. Compare source and restored migration ledger, row count, ordered manifest,
   and backup checksum. Retrieve and SDK-verify every restored snapshot.
7. Record results, revoke restore credentials, destroy the restore target, and
   securely remove the local backup after it reaches its separately approved
   backup-retention destination.

## 5. Rollback rehearsal

1. Keep capture disabled.
2. Record current row count, manifest, private API deployment, and TraderNow
   revision.
3. Roll the private API back to the previous deployment or stop it.
4. Verify TraderNow health, revision, and latency are unchanged.
5. Verify the snapshot database remains readable and its row count and manifest
   are unchanged.
6. Restore the candidate private API deployment with capture still disabled.
7. Verify health returns `200`, authenticated readiness returns the expected
   `503 service_disabled`, read routes remain available, and stored integrity
   still passes.
8. Temporarily enable capture only if successful `200` readiness itself must be
   recertified; perform no capture, verify readiness, and immediately disable
   it again.

Rollback never deletes or updates snapshots.

## 6. Controlled production shadow

Proceed only after independent confirmation that every preceding mandatory
item passed.

1. Record TraderNow health, revision, availability, and a bounded latency
   sample immediately before capture.
2. Enable capture for a bounded operator window.
3. Perform one explicit capture for approved `MNQ`, `5m`,
   `displacement_volume_context`.
4. Verify persistence, canonical bytes, metadata, digest, identity,
   correlation ID, and retrieval.
5. Repeat once and verify idempotent duplicate behavior without a second row.
6. Disable capture immediately.
7. Record the same TraderNow health, revision, availability, and latency sample.
   Compare before/after and investigate any material regression.

No schedule, retry worker, background task, public domain, AI operation, or
automatic capture is permitted.

## 7. Cleanup, retention, and approval

Retain until Phase 17E approval:

- isolated source snapshot database and volume;
- private API service with capture disabled;
- approved release commit and deployment ID;
- encrypted approved backup, if retention is required;
- sanitized certification evidence bundle.

Remove or revoke:

- restore target;
- ephemeral maintenance process;
- temporary administrative configuration;
- disposable restore credentials;
- superseded runtime credentials after successful rotation;
- local unencrypted backup and scratch files.

Do not remove immutable snapshots or the source database. Record every retained
and removed resource in `11-cleanup.txt`. A reviewer must verify the evidence
manifest, privileges, no-public-domain state, disabled capture, unchanged
TraderNow revision, and all mandatory results before declaring Phase 17E
operationally certified.

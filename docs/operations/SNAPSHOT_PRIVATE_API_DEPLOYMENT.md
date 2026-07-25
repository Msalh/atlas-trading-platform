# Private Snapshot API Deployment Contract

This document is the deployment contract for the Phase 17E private Snapshot
API. It does not authorize deployment or operational certification.

## Service boundary

- Service name: `snapshot-private-api`
- Source root: `live/`
- Runtime module: `atlas_snapshot_api.runtime`
- ASGI object: `app`
- Python: 3.12
- Replicas: one for the Phase 17E internal certification
- Networking: Railway private network only; do not create a service or custom
  domain
- Capture state at initial deployment: disabled
- Scheduler, cron, worker, AI provider, and public ingress: absent

The existing `live/Procfile` belongs to the general Atlas service and must not
be used or changed for this service.

## Build and start

Use the repository's reviewed Phase 17 release commit and `live/` as the source
root. Install `live/requirements.txt`.

Set this exact Railway start-command override on the private service:

```text
uvicorn atlas_snapshot_api.runtime:app --host 0.0.0.0 --port $PORT
```

The runtime imports configuration from the environment, creates independent
writer and reader pools, and starts them during ASGI lifespan. A missing or
invalid required variable must fail startup. Do not replace that failure with
defaults.

Package from a clean checkout or reviewed archive. `live/.railwayignore`
excludes tests, caches, bytecode, temporary directories, logs, and deployment
bundles. Before upload, verify that the archive contains `atlas_snapshot`,
`atlas_snapshot_store`, `atlas_snapshot_capture`, `atlas_snapshot_api`,
`snapshot_migrations`, and `specs/trader_now_snapshot`, but none of the ignored
material.

## Required environment

| Variable | Purpose and format | Validation | Security and rotation |
|---|---|---|---|
| `SNAPSHOT_WRITER_DATABASE_URL` | Psycopg PostgreSQL connection URI/conninfo for the isolated writer login. It must select `atlas_snapshot_writer` through controlled `options=-c role=atlas_snapshot_writer`. | Required at import; pool must open; runtime privilege audit must show only `SELECT` and `INSERT`. | Secret. Never log or place in a file, command history, evidence bundle, or deployment message. Rotate by creating a new login credential, updating the variable, restarting only this service, verifying, then revoking the old login. |
| `SNAPSHOT_READER_DATABASE_URL` | Psycopg PostgreSQL connection URI/conninfo for a distinct isolated reader login, selecting `atlas_snapshot_reader`. | Required at import; pool must open. Runtime also sets `default_transaction_read_only=on`; privilege audit must be `SELECT` only. | Secret. Apply the same staged credential rotation and redaction rules as the writer URL. |
| `TRADER_NOW_BASE_URL` | Private origin only, for example `http://trader-now-read-only.railway.internal:<port>`. Do not include a path, query, fragment, username, or password. | Required. Scheme must be `http` or `https`; hostname required; embedded credentials, query, and fragment rejected. | Configuration, not a credential, but treat private host details as internal operational data. Change only after endpoint health and revision verification. |
| `TRADER_NOW_API_KEY` | Bearer credential accepted by the private TraderNow service. | Required and non-blank. Authentication is verified during smoke capture. | Secret. Never log or expose in evidence. Rotate at the owning service, update this service, run an authenticated read, then revoke the old key. Rotation must not restart or redeploy TraderNow unless separately authorized. |
| `SNAPSHOT_CAPTURE_ENABLED` | Exact lowercase boolean `true` or `false`. Initial and rollback value is `false`. | Any other value fails startup. Capture and successful readiness require `true`. | Non-secret. Every change is an operator-controlled certification event. Return to `false` immediately after each bounded window. |
| `SNAPSHOT_READER_API_TOKEN` | High-entropy bearer token for read, metadata, integrity, listing, and readiness operations. | Required, non-empty, and different from the operator token. | Secret. Generate with a cryptographically secure generator using at least 32 random bytes. Rotate independently and never include it in logs, screenshots, evidence, URLs, or shell history. |
| `SNAPSHOT_OPERATOR_API_TOKEN` | High-entropy bearer token for capture plus all reader operations. | Required, non-empty, and different from the reader token. | Secret. Apply the same generation and redaction rules. Rotate after certification or any suspected exposure. |

Railway variables must be configured directly on this private service. Do not
use production database credentials, share another service's database, or give
the runtime migration, retention, ownership, role-administration, or
superuser authority.

## Health and readiness

- `GET /health` is unauthenticated and process-only.
- `GET /readiness` requires reader or operator authentication.
- With capture disabled, readiness intentionally returns
  `503 service_disabled`. This is the expected safe initial and rollback state.
- With capture enabled, readiness succeeds only if configuration, writer-store
  access, and reader-store access are available.

Never configure Railway's deployment health check to require successful
`/readiness` while capture is disabled. If a platform check is required, use
`/health`; certification validates authenticated readiness separately.

## Assumptions and stop conditions

- The isolated PostgreSQL service and least-privilege roles already exist.
- Migration `0001_snapshot_store.sql` is recorded in the migration ledger.
- TraderNow remains independently deployed, private, healthy, and unchanged.
- No public domain exists before or after deployment.
- Any startup failure, unexpected domain, privilege excess, schema mismatch,
  unsanitized error, or evidence-integrity failure stops certification.

Deployment and capture require explicit approval after Railway provisioning is
available.

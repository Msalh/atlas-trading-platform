# Private Snapshot API Operator Reference

Schema version: `snapshot_private_api.v1`

This API is private, read-mostly, and operator-triggered. OpenAPI, Swagger, and
ReDoc are intentionally disabled. All snapshot routes use bearer
authentication. The reader token may read; the operator token may read and
capture.

## Common behavior

- Supply `Authorization: Bearer <token>`.
- An optional `X-Correlation-ID` must match
  `[A-Za-z0-9._:-]{1,128}`. Invalid or missing values are replaced with a
  server UUID; the effective value is returned in the response header.
- Structured capture/store errors include the effective correlation ID.
- Reader and operator read requests share separate per-role, per-process
  limits of 120 requests per 60 seconds.
- Operator capture is limited to 10 requests per 60 seconds.
- Limits reset when the single private API process restarts. They are a safety
  throttle, not a distributed quota.
- No response contains database URLs, API tokens, infrastructure exceptions,
  or TraderNow credentials.

## Status routes

### `GET /health`

Authentication: none. Rate limit: none.

`200`:

```json
{"ok":true,"service":"atlas-snapshot-private-api","code":null}
```

This proves process health only.

### `GET /readiness`

Authorization: reader or operator.

- `200`: capture is enabled and both writer and reader store paths are ready.
- `401`: missing or invalid token.
- `503 service_disabled`: expected while capture is disabled.
- `503 configuration_unavailable`, `not_started`,
  `snapshot_store_unavailable`, or `snapshot_reader_unavailable`: dependency
  is not ready.

## Capture

### `POST /api/v1/snapshots/capture`

Authorization: operator only. Reader receives `403`. Rate limit: 10/minute.

Exact request:

```json
{
  "symbol": "MNQ",
  "timeframe": "5m",
  "strategy_id": "displacement_volume_context"
}
```

Extra fields or any other identity are rejected.

- `201`: a new immutable snapshot was inserted and read back successfully.
- `200`: matching evidence already exists; `disposition` is `duplicate`.
- `400`: invalid request or unapproved identity.
- `401`/`403`: authentication or authorization failure.
- `409`: conflicting idempotency identity.
- `422`: transport validation failure.
- `429`: capture rate exceeded.
- `502`: upstream authentication, authorization, schema, response, or SDK
  projection/validation failure.
- `503`: capture disabled, configuration unavailable, store unavailable,
  upstream unavailable, or upstream timeout.

Successful response fields are:

```json
{
  "schema_version": "snapshot_private_api.v1",
  "disposition": "created",
  "snapshot_id": "<uuidv7>",
  "evidence_digest": "<64 lowercase hex>",
  "idempotency_key": "tns1:<64 lowercase hex>",
  "correlation_id": "<effective correlation id>",
  "metadata": {"schema_version": "snapshot_private_api.v1"}
}
```

Capture is disabled by default and has no scheduler, retry worker, or automatic
invocation.

## Retrieval

### `GET /api/v1/snapshots/{snapshot_id}`

Authorization: reader or operator. Rate limit: 120/minute per role.

- `200`: verified canonical evidence projected as JSON under `snapshot`.
- `404`: snapshot not found.
- `409`: stored evidence failed integrity verification.
- `422`: malformed UUID.
- `429`: read limit exceeded.
- `503`: snapshot store unavailable.

### `GET /api/v1/snapshots/{snapshot_id}/metadata`

Returns verified, derived, non-authoritative indexed metadata. Status behavior
matches snapshot retrieval.

### `GET /api/v1/snapshots/{snapshot_id}/integrity`

`200` returns:

```json
{
  "schema_version": "snapshot_private_api.v1",
  "snapshot_id": "<uuidv7>",
  "evidence_digest": "<64 lowercase hex>",
  "valid": true
}
```

Invalid evidence is never returned as valid and is never repaired.

### `GET /api/v1/snapshots?limit=50&cursor=<opaque>`

Authorization: reader or operator. Rate limit: 120/minute per role.

- `limit` defaults to 50 and must be 1–100.
- `cursor` is optional, opaque, and limited to 1,024 characters.
- Results contain verified metadata and an optional `next_cursor`.
- `400`: invalid cursor.
- `422`: invalid query shape.

## Error envelope

Sanitized handled failures use:

```json
{
  "schema_version": "snapshot_private_api.v1",
  "code": "<stable code>",
  "message": "<safe message>",
  "correlation_id": "<effective correlation id>"
}
```

Operators must record correlation IDs, status codes, snapshot IDs, and digests,
but must never record bearer tokens, DSNs, raw exception strings, or private
credentials.

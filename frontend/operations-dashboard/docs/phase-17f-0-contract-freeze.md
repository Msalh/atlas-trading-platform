# Phase 17F-0 Contract Freeze

This document records the reader-only Phase 17E transport surface consumed by
the Phase 17F Semantic Evidence MVP. It is derived from the frozen local
`atlas_snapshot_api` implementation at revision `d14b930`.

This is a local development contract. Operational behavior remains subject to
confirmation after Phase 17E receives GO.

## Reader routes

| Capability | Method | Private Snapshot API route |
| --- | --- | --- |
| Bounded list | `GET` | `/api/v1/snapshots?limit={1..100}&cursor={opaque}` |
| Semantic detail | `GET` | `/api/v1/snapshots/{snapshot_id}` |
| Indexed metadata | `GET` | `/api/v1/snapshots/{snapshot_id}/metadata` |
| Integrity | `GET` | `/api/v1/snapshots/{snapshot_id}/integrity` |

No capture, digest lookup, canonical-byte, mutation, generic-proxy, or database
surface belongs to Slice 17F-1.

## Frozen transport facts

- API schema version: `snapshot_private_api.v1`
- Snapshot path identity: UUID
- Default list limit: `50`
- Maximum list limit: `100`
- Upstream cursor maximum: `1024` characters
- Cursor semantics: opaque to the browser and BFF
- Correlation response header: `X-Correlation-ID`
- Authentication: server-held reader bearer principal
- Detail response: semantic JSON transport representation
- Successful integrity response: identity, evidence digest, and literal
  `valid: true`
- Integrity failure: sanitized `409` with
  `code=snapshot_integrity_failed`
- Missing snapshot: sanitized `404` with `code=snapshot_not_found`
- Store unavailable: sanitized `503` with
  `code=snapshot_store_unavailable`

## Authority labels

The detail representation must be labeled **Semantic snapshot JSON**.

It must not be labeled canonical JSON, raw canonical payload, stored bytes,
byte-identical evidence, or whole-file artifact. Slice 17F-1 has no canonical
download.

Indexed metadata is derived and non-authoritative. Integrity success means the
Snapshot SDK verified the stored snapshot before the API returned the success
response. Integrity failure must suppress evidence content in later increments.

## Fixture policy

All frontend fixtures use synthetic UUIDs, digests, series identities,
timestamps, cursors, and correlation IDs. They contain no real tokens, private
hostnames, DSNs, production evidence, or infrastructure exceptions.

Fixtures model the frozen transport contract, not PostgreSQL rows or canonical
UTF-8 bytes. They must never be treated as evidence-authority test vectors.

## Post-GO confirmations

Before Increment 17F-5B, compare the certified private environment with this
contract and explicitly confirm:

1. Response models and status codes.
2. Reader authentication behavior.
3. Private-network reachability.
4. Real latency and timeout suitability.
5. Unsupported-schema response behavior.
6. Correlation-header behavior.

Any difference must update the contract tests through review; it must not be
silently normalized.

## Contract-freeze checklist

The following assumptions are frozen for local Slice 17F-1 development:

- [x] Private API transport version is `snapshot_private_api.v1`.
- [x] Snapshot envelope schema version is `trader_now_snapshot.v1`.
- [x] Snapshot path identity is a syntactically valid UUID; approved snapshot
  fixtures use UUIDv7.
- [x] Evidence digest is lowercase, 64-character SHA-256 hexadecimal.
- [x] List cursors are optional, server-issued opaque strings with a maximum
  inbound length of 1024 characters. The browser and BFF never decode them.
- [x] Correlation identity is returned through `X-Correlation-ID`.
- [x] Successful reader routes return `200`.
- [x] Invalid cursors return `400`.
- [x] Missing or invalid bearer authentication returns `401`.
- [x] An authenticated principal without required authority returns `403`.
- [x] A missing snapshot returns `404`.
- [x] Snapshot integrity failure returns `409`.
- [x] Rate limiting returns `429`.
- [x] Snapshot-store unavailability returns `503`.
- [x] FastAPI request-shape validation may return `422`.
- [x] Sanitized domain errors use the `snapshot_private_api.v1` error envelope:
  `schema_version`, `code`, `message`, and `correlation_id`.
- [x] Framework-generated `400`, `401`, `403`, `422`, and `429` responses are
  not assumed to use the domain error envelope; the BFF must translate them
  into its own sanitized, stable error contract.
- [x] Operational equivalence remains unverified until Phase 17E receives GO.

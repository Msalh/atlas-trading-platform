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

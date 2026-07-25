# TraderNow Snapshot Specification v1

Status: Phase 17A frozen specification. This directory contains no runtime
implementation.

## Contract identities

| Concern | Identifier |
|---|---|
| Snapshot schema | `trader_now_snapshot.v1` |
| Evidence profile | `trader_now_complete.v1` |
| Canonicalization profile | `atlas-jcs.v1` |
| Digest algorithm | `sha256` |

An evidence snapshot is an immutable, allowlisted projection of exactly one
validated TraderNow transport response. Snapshot creation is external to
TraderNow. The snapshot is not a TraderNow domain object, API response, AI input,
AI output, or audit record.

## Envelope

The authoritative payload is the complete canonical JSON document described by
`schema.json`. It contains:

- contract and canonicalization identities;
- snapshot and idempotency identities;
- capture and evaluation times;
- supported source schema versions;
- the allowlisted deterministic evidence;
- a digest descriptor.

The canonical digest preimage contains exactly
`snapshot_schema_version`, `evidence_profile`, `canonicalization_profile`,
`source`, and `evidence`. Record metadata (`snapshot_id`, `idempotency_key`,
`supersedes_snapshot_id`, `created_at`) and the `integrity` descriptor are not
evidence and are excluded. After hashing, the lowercase 64-character SHA-256
hexadecimal digest is inserted into `integrity.evidence_digest`. Verification
reconstructs the evidence preimage and compares the digest in constant time.

## Snapshot identity

`snapshot_id` is a lowercase RFC 9562 UUIDv7 string. It identifies the immutable
stored record; it is not a content address.

The evidence digest identifies canonical content. Snapshot ID and evidence digest
must remain distinct because record addressing and content integrity have
different lifecycles.

Corrections create a new snapshot ID and digest. The new envelope sets
`supersedes_snapshot_id` to the earlier record. The earlier record is never
modified.

## Idempotency identity

`idempotency_key` has this normative form:

`tns1:<sha256-lowerhex>`

Its digest preimage is canonical `atlas-jcs.v1` JSON containing exactly:

- evidence profile;
- economic instrument;
- market-data provider, source symbol, series type, and resolution version;
- timeframe;
- latest closed bar time, including explicit `null`;
- strategy ID and version;
- sorted engine/definition version identities;
- freshness policy version;
- evaluation time.

Including evaluation time makes freshness/trust classifications part of capture
identity. Retries must reuse the original evaluation time and idempotency key.
Equal keys with unequal canonical payloads are integrity conflicts, never
overwrites.

## Authoritative and derived data

The canonical payload is the sole authoritative representation. Future indexed
metadata is derived from it and is non-authoritative. Phase 17A defines no
persistence, metadata store, API, or service.

## Evidence rules

The allowlist is normative and exhaustive. Unknown source fields are ignored
during projection; unknown fields in a completed snapshot are invalid.
Unavailable and insufficient-data sections are explicit and are never omitted.
Ordered Rule, Setup, Interpretation, Strategy, and reason-code arrays retain
their semantic order.

The snapshot contains the canonical composed analysis only. It does not contain
the complete MarketState history. `MarketWindowArtifact` is outside this release.

## Version evolution

- Stored v1 envelopes are never rewritten.
- A change to meaning, required fields, decimal precision, timestamp precision,
  digest construction, or canonicalization requires a new version.
- Additive optional fields require a compatibility review; they do not
  automatically qualify as v1-compatible because `additionalProperties` is
  forbidden.
- Derived conversions create new immutable records and reference their source.
- Readers must explicitly declare supported snapshot, evidence, and
  canonicalization profiles.
- No version may reinterpret a historical enum value.

## Supported source

This version supports `trader_now_response.v2` derived from `trader_now.v2`.
Other source versions must be rejected.

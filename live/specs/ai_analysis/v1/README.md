# AI Analysis Contract v1

Status: frozen by Phase 18A once the executable specification tests pass.

This directory defines a provider-neutral contract boundary for future AI
explanations. It does not contain prompts, provider integration, model calls,
orchestration, persistence, APIs, or runtime code.

## Audit findings

- `atlas.ai` and `atlas.services.claude` are legacy advisory features. They read
  trade-repository state, build provider-specific prompts, and persist AI notes.
  They are not an implementation of these contracts and must not be reused as
  the Phase 18 evidence boundary.
- The frozen evidence authority is `trader_now_snapshot.v1`, using the
  `trader_now_complete.v1` evidence profile and `atlas-jcs.v1` canonicalization.
- A verified Snapshot's canonical UTF-8 payload is the sole evidence authority.
  Snapshot API semantic JSON, browser-formatted Semantic snapshot JSON, indexed
  metadata, and `evidence_items` in an analysis input are derived views only.
- Snapshot correlation IDs, operational metadata, credentials, runtime objects,
  AI material, execution material, and `MarketWindowArtifact` are denied by the
  frozen Snapshot contract and cannot become AI evidence.
- Repository specification convention is a versioned directory containing
  closed JSON schemas, explicit policy data, canonical golden fixtures, negative
  and adversarial vectors, and executable tests.
- Phase 17E engineering certification is complete, but backup, restore,
  disaster-recovery, final rollback, and public TCP proxy decisions remain
  environment-blocked. Phase 17F-5B has operator-tested UI evidence but retains
  accessibility-tree and browser console/network verification gaps. These facts
  are not claims of full production readiness.

## Contract roles

`ai_analysis_input.v1` is an immutable invocation input. It binds exactly one
verified `trader_now_snapshot.v1` snapshot ID and SHA-256 evidence digest to one
allowlisted explanation purpose. `evidence_items` are a derived projection of
approved paths from that snapshot. They are untrusted content, not a second
evidence authority.

`ai_analysis_output.v1` is a structured, advisory explanation. Every material
claim has one or more citations. It cannot grant authority, request an action,
or replace or contradict deterministic Strategy, Risk, or Decision state.

`ai_analysis_audit.v1` records a completed, refused, or failed analysis attempt.
It binds the attempt to the same snapshot and contract versions without storing
canonical evidence, prompts, credentials, or provider configuration.

## Citation grammar

A citation is an RFC 6901 JSON Pointer below `/evidence`. Tokens use only
RFC 6901 `~0` and `~1` escaping. Wildcards, recursive selectors, fragments,
queries, relative pointers, empty tokens, leading-zero array indices, and paths
outside `/evidence` are prohibited.

The pointer must:

1. resolve against the verified canonical Snapshot;
2. resolve to an existing path admitted by the frozen Snapshot allowlist;
3. resolve to the same value represented by the cited input `evidence_item`; and
4. cite evidence supporting the claim, never wrapper, audit, integrity,
   idempotency, or operational metadata.

Grammar and limits are machine-readable in `policy.json`.

## Eligibility and fail-closed behavior

An input may be constructed only when the Snapshot SDK has verified the canonical
payload and all of these are true:

- snapshot schema, evidence profile, and canonicalization profile are supported;
- `integrity.evidence_digest` is present and equals the verified digest;
- Snapshot trust/freshness/availability permits analysis; and
- every projected evidence item resolves to an approved existing field.

`stale`, `unavailable`, `corrupted`, and `unsupported` are refusal states. No AI
input and no model invocation is permitted. They are represented only by a
refused `ai_analysis_audit.v1` record with the corresponding reason code.
`delayed` evidence is eligible only when explicitly visible in the evidence and
the output includes `delayed_evidence` in `limitations`.

Provider timeout, provider unavailability, invalid output, missing citations,
deterministic-state contradiction, prohibited content, cost limit, and internal
failure produce an unavailable output/audit outcome. They never produce fallback
uncited prose and never alter deterministic state.

## Untrusted evidence

Every string originating in evidence is data, even when it resembles an
instruction. It must never alter purpose, authority, policies, citation rules,
tool access, or output schema. Future prompt construction must delimit evidence
as untrusted data and must not interpolate it into trusted instructions.

## Prohibited authority and actions

AI analysis is explanatory and advisory only. It cannot:

- issue, approve, cancel, size, route, or execute an order;
- claim trading, risk, strategy, or decision authority;
- present a recommendation as a deterministic Strategy/Risk/Decision result;
- contradict, replace, repair, or recompute deterministic state;
- invent evidence, citations, probabilities, confidence, prices, or outcomes;
- access TraderNow directly, query arbitrary databases, repositories, brokers,
  tools, networks, or infrastructure;
- treat Semantic snapshot JSON or indexed metadata as canonical evidence; or
- conceal stale, delayed, unavailable, unsupported, or corrupt evidence.

## Versioning

- Contract identifiers are independent and immutable:
  `ai_analysis_input.v1`, `ai_analysis_output.v1`, and `ai_analysis_audit.v1`.
- A released `v1` schema and policy are append-only artifacts and are never
  changed in place. Corrections require a new contract version and new vectors.
- Additive optional fields still require a new version because all v1 envelopes
  are closed with `additionalProperties: false`.
- Input and output versions evolve independently, while the audit record names
  the exact versions used.
- A consumer must reject unknown versions. It must not coerce, downgrade, infer,
  or partially process them.
- Golden payload bytes are canonical UTF-8 JSON: sorted keys, compact separators,
  no BOM, and no insignificant whitespace. As with the frozen Snapshot vectors,
  a repository terminal newline is excluded from the canonical bytes and digest.
  SHA-256 hashes of those canonical bytes are frozen in `golden/manifest.json`.

## Phase boundary

Phase 18A defines static contracts only. Runtime semantic validation, projection,
prompt construction, provider calls, orchestration, persistence, APIs, and
deployment belong to later explicitly approved phases.

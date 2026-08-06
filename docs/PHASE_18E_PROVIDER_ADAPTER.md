# Phase 18E — Offline Concrete Provider Adapter Contract and Qualification Harness

Status: independently certified offline-complete and default-disabled. Phase 18E
is ordered after the completed Phase 18D. Phase 3A adds one independently
reviewable, expiring pricing record; runtime binding and provider calls remain
separately blocked.

This document authorizes isolated implementation and offline qualification only.
It authorizes no credential use, provider or network call, runtime integration,
deployment, or operational certification.

## Objective and authority boundary

Phase 18E will implement exactly one concrete provider adapter behind the
existing `atlas_ai_orchestration.ProviderPort` and qualify it with offline fakes,
fixtures, and deterministic local stubs. The adapter transports one immutable
`TrustedProviderRequest` and returns one untrusted provider candidate to the
Phase 18D core. Phase 18B remains the sole authority that validates or trusts an
`ai_analysis_output.v1` value.

The adapter has transport authority only. It has no evidence, citation,
strategy, risk, decision, audit, persistence, broker, or execution authority.

## Approved implementation decisions and deferred operational gate

| Decision | Required disposition |
|---|---|
| Initial provider target | OpenAI, offline adapter qualification only. Account access and operational entitlement remain unverified. |
| Integration boundary | Direct non-streaming HTTP through one adapter-owned `httpx.Client.send`. The production client is constructed internally; offline qualification may inject only an `httpx.BaseTransport`, never a configured client. |
| Dependency version and lock policy | `httpx==0.28.1`; runtime installation is prohibited. No transitive lockfile or hashes exist, so reproducible deployment remains unclaimed and blocked pending transitive locking. |
| Secret owner | Security/Platform for later operational enablement. Phase 18E reads no environment or credential store. |
| Accepted model allowlist | Explicitly injected and non-empty. Phase 3 policy accepts exactly `gpt-5.6-terra` for a local manual experiment without claiming immutability; production approval remains deferred. |
| Request-byte ceiling | 65,536 serialized bytes. |
| Response-byte ceiling | 131,072 streamed bytes. |
| Transport timeout | 5-second connect, 45-second read, 60-second end-to-end deadline. |
| Maximum input/output tokens | 16,384 input and 4,096 output. |
| Estimated pre-call cost ceiling and units | USD 0.12 maximum standard/default token charge. A package-owned pricing catalog binds an integrity-protected record to an opaque reference, provider, exact model, rates, USD-per-million-token unit, service tier, independently approved source/version, catalog version/digest, effective time, verification time, expiry, and maximum age. The catalog rejects every duplicate exact provider/model/service-tier identity, including semantic duplicates under different references. The authority gate always calculates cost with package-owned maxima of 16,384 input and 4,096 output tokens using deterministic decimal arithmetic; caller request limits cannot reduce it. Missing, conflicting, stale, future-effective, mismatched, unsupported, integrity-invalid, or over-ceiling metadata fails before prompt construction, credentials, client creation, or transport. Phase 3A approves one dated default-tier `gpt-5.6-terra` record observed 2026-08-06 and expiring 2026-09-05; it is reviewable pricing evidence, not a permanently immutable price. |
| Decoded JSON-domain return type | Recursive `JSONValue`: exact JSON scalar, list, or string-keyed dictionary values without `Any`, coercion, envelope, or sentinel. |
| Absent-candidate classification | Sanitized `ProviderUnavailableError`, routed by Phase 18D to `provider_unavailable`; no fabricated candidate. |

Only the approved ceilings may be defaults. Provider/model identity, enablement,
pricing verification, and credential supply remain explicit and fail closed. The
request-policy caller supplies only an exact pricing-reference identifier; it
cannot supply rates, records, sources, versions, approval allowlists, catalogs,
authority objects, or an approval capability. Offline tests replace the resolver
symbol only through pytest monkeypatch with a fixed qualification catalog. That
test-only replacement is not accepted by the adapter constructor or policy and
is not exposed by any runtime factory or configuration loader.

Cached-input pricing is not represented by the existing catalog schema or cost
equation, so Phase 3A does not add or claim the separately quoted cached-input
rate. Standard input and output rates remain the conservative authority inputs.

Caller-configurable token limits remain bounded request controls only. They may
lower the size of a particular offline-qualified request, but never replace or
reduce the fixed authority-level 16,384/4,096 calculation. The Phase 3A record
uses the official OpenAI pricing announcement at
`https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/`,
observed 2026-08-06. Resolution fails closed at its 2026-09-05 review deadline.
The authority rejects both a declared maximum age and a verified-to-expiry
window greater than 2,592,000 seconds, even when a changed catalog has a newly
computed digest.

The request explicitly selects `service_tier: "default"`, the documented
standard pricing/performance tier. It also selects explicit prompt-caching mode
without marking any cache breakpoint. Current OpenAI guidance documents that
implicit mode performs automatic caching and that explicit mode caches only
marked reusable prefixes; it does not document a separate universal caching-off
field. Operational enablement therefore remains blocked unless independent
review confirms that the selected model/endpoint honors the no-breakpoint
explicit-mode policy as no cache write, or approves the resulting retention and
pricing behavior. The implementation makes no claim that caching is universally
disabled.

## Transport ownership and dispatch proof

The adapter accepts no preconfigured `httpx.Client`, authentication object,
event hook, mount, proxy, or redirect policy. Its owned client fixes
`trust_env=False`, HTTP/2 off, redirects off, `auth=None`, empty event hooks, no
mounts or proxy, explicit connect/read/write/pool timeouts, one connection, no
keep-alive pool, and `httpx.HTTPTransport(retries=0)`. Offline tests inject only
a counting or mock transport at the `BaseTransport` boundary.

Qualification proves one application `httpx.Client.send` dispatch and one
injected `transport.handle_request` invocation after acceptance, and zero
transport invocations for pre-transport rejection. It does not claim one DNS,
TCP, TLS, or socket operation inside the platform transport.

Every response and client cleanup boundary translates hostile close failures to
an existing empty typed adapter failure, removes cause/context, and preserves a
more authoritative timeout or unavailable classification already selected.

## Existing Phase 18D boundary

The adapter input is the frozen, immutable `TrustedProviderRequest` containing:

- trusted instruction strings;
- explicitly delimited untrusted evidence JSON;
- analysis output/input and Snapshot identities;
- evidence digest and allowlisted purpose; and
- the required output schema version.

The adapter must not add canonical Snapshot wrappers, audit metadata,
credentials, endpoints, pricing data, operational metadata, or trading material
to that request.

`ProviderPort.invoke()` returns the recursive `JSONValue` contract. A decoded
JSON candidate must be returned without coercion. Phase 18D passes it exactly
once to the real Phase 18B
`validate_output()` boundary; an invalid envelope or invalid semantic content is
therefore classified through the existing `invalid_output` route.

The recursive `JSONValue` alias is shared from the Phase 18B model module, and
`validate_output()` accepts that type directly. Phase 18B performs the top-level
object rejection itself and remains the sole semantic authority; Phase 18D does
not narrow, coerce, wrap, or fabricate candidates.

`ProviderPort` also exposes a structural, non-secret `GeneratorIdentity`.
Phase 18D compares it exactly with the audit generator before prompt building,
cost evaluation, or provider invocation. Missing, malformed, provider-mismatched,
or model-mismatched identity follows the existing sanitized
`internal_unavailable` audit route with zero provider dispatches. The supplied
audit identity is never rewritten, and the core has no concrete adapter check.

Validly decoded JSON scalars, arrays, and JSON `null` fit this contract and pass
unchanged to Phase 18B. Decoded JSON `null` is a candidate value and remains
distinct from an absent provider candidate.

When a candidate is absent, no value exists to pass unchanged. When JSON is
malformed or decoding raises, no decoded candidate exists. Broadening the port
type does not solve either case. Under the minimal current contract, malformed
JSON and decoder exceptions are sanitized `internal_unavailable` failures with
no retained raw material, cause, or context. Mapping either case to
`invalid_output` would require an explicitly approved new typed adapter failure
and corresponding Phase 18D routing change. An absent candidate is sanitized as
provider unavailable.

The adapter must never manufacture an empty mapping, sentinel, response envelope,
or plausible analysis envelope to conceal an absent, malformed, or invalid
provider response. No new untrusted response envelope is authorized by this
definition.

## Adapter call contract

For one eligible Phase 18D request, the adapter must:

1. validate non-secret configuration and fixed ceilings before transport;
2. reject a request exceeding the approved byte or token boundary before any
   provider call;
3. perform exactly one provider operation with the explicit model ID only after
   it matches the injected allowlist;
4. enforce the approved timeout in the concrete transport;
5. bound response bytes before full decoding where the selected mechanism
   permits;
6. decode at most one provider result without coercing, repairing, completing,
   or semantically validating it;
7. when decoding produces a candidate, return that untrusted value unchanged to
   Phase 18D for its single Phase 18B validation; and
8. discard the request, raw response, and all provider diagnostics after the
   call.

The adapter performs no retry, backoff, alternate-model request, fallback
provider call, tool call, retrieval, or streaming continuation.

## Failure translation

| Condition | Adapter behavior | Phase 18D public classification |
|---|---|---|
| Phase 18C refusal | Adapter is not invoked. | Existing refused audit. |
| Cost-policy rejection | Adapter is not invoked. | `cost_limit` failed audit. |
| Missing/invalid non-secret configuration | Fail before transport with a sanitized adapter configuration failure. | `internal_unavailable`; no retry. |
| Missing credential | Fail closed before transport without naming or inspecting the value. | `internal_unavailable`; no retry. |
| Request exceeds approved ceiling | Fail before transport with no provider call. | `internal_unavailable`; no retry. |
| Transport timeout | Raise only `ProviderTimeoutError` with no raw cause, context, response, or diagnostic. | `provider_timeout`. |
| Provider/service unavailable | Raise only `ProviderUnavailableError` with no raw cause, context, response, or diagnostic. | `provider_unavailable`. |
| Provider-level refusal with no output candidate | Raise sanitized `ProviderUnavailableError`; do not fabricate an unavailable analysis envelope. | `provider_unavailable`. |
| Response exceeds approved ceiling | Abort/discard and raise sanitized `ProviderUnavailableError`. | `provider_unavailable`. |
| Decoded mapping with valid envelope/content | Return unchanged as untrusted data. | Determined exclusively by Phase 18B validation. |
| Decoded mapping with invalid envelope/content | Return unchanged; do not inspect, repair, or classify in the adapter. | Real Phase 18B rejection through existing `invalid_output` routing. |
| Decoded scalar | Return unchanged; no coercion to a mapping. | Real Phase 18B rejection through `invalid_output`. |
| Decoded array | Return unchanged; no coercion, extraction, or wrapping. | Real Phase 18B rejection through `invalid_output`. |
| Decoded JSON `null` | Preserve as a candidate and do not confuse it with absence. | Real Phase 18B rejection through `invalid_output`. |
| Absent candidate | Raise sanitized `ProviderUnavailableError`; never fabricate a sentinel or envelope. | `provider_unavailable`. |
| Malformed JSON / normal decode rejection | Discard raw bytes and fail without constructing a candidate. | `internal_unavailable` under the current contract. A future `invalid_output` mapping requires a new typed failure and approved Phase 18D routing change. |
| Decoder exception | Catch and translate without preserving raw material, cause, context, or diagnostics. | `internal_unavailable` under the current contract. A distinct route requires explicit Phase 18D approval. |
| Unexpected SDK/transport failure | Catch and translate without preserving the original exception chain. | `internal_unavailable`; no retry. |

Sanitized typed failures must be raised outside the provider exception handler,
or otherwise constructed so both `__cause__` and `__context__` are absent. Raw
provider exception text must never be parsed to choose a public reason.

## Secret and configuration boundary

The proposed configuration names are names only; no values are authorized:

| Name | Classification | Rule |
|---|---|---|
| `ATLAS_AI_PROVIDER_ENABLED` | Non-secret | Defaults disabled. Only the explicit enabled value may permit adapter construction. |
| `ATLAS_AI_PROVIDER_API_KEY` | Server-only secret | Read only by the concrete adapter factory; never stored on a request or public outcome. |
| `ATLAS_AI_PROVIDER_MODEL` | Non-secret | A later runtime factory may supply it only after immutable-model approval; the offline adapter accepts an explicitly injected value that must exactly match its injected allowlist. |
| `ATLAS_AI_PROVIDER_TIMEOUT_SECONDS` | Non-secret | Must equal or be stricter than the approved timeout policy. |
| `ATLAS_AI_PROVIDER_MAX_REQUEST_BYTES` | Non-secret | Fail closed before transport when absent, invalid, or exceeded. |
| `ATLAS_AI_PROVIDER_MAX_RESPONSE_BYTES` | Non-secret | Fail closed when absent, invalid, or exceeded. |
| `ATLAS_AI_PROVIDER_MAX_OUTPUT_TOKENS` | Non-secret | Passed only as an approved bounded provider option. |
| `ATLAS_AI_PROVIDER_MAX_ESTIMATED_COST` | Non-secret | Evaluated by the trusted pre-call cost policy using approved units. |

The secret value and every derivative are prohibited from prompts, provider
request bodies other than the transport authentication mechanism, outcomes,
audits, exception text, causes, contexts, tracebacks, logs, metrics, fixtures,
snapshots, test reports, repository files, and evidence artifacts.

Diagnostics are allowlisted aggregates only: fixed failure category, adapter
version identity, approved non-secret provider/model identity, and bounded timing
category where later observability policy permits it. Raw request/response bodies,
headers, endpoints, credential properties, and provider diagnostics are denied.

## Operational ceilings

Phase 18E must implement fixed validated policy values, not permissive defaults:

| Ceiling | Required value |
|---|---|
| Maximum serialized trusted request bytes | 65,536 |
| Maximum provider response bytes | 131,072 |
| Connect/read/end-to-end timeout | 5 / 45 / 60 seconds |
| Maximum input/output tokens | 16,384 / 4,096 |
| Maximum estimated pre-call cost and units | USD 0.12 standard token charge |
| Exact provider/model allowlist | Explicit injection required; production identifier deferred |

Absent, malformed, non-finite, negative, zero where invalid, or out-of-policy
values fail closed before transport. Provider and model identities recorded in a
Phase 18B audit come only from the approved non-secret `GeneratorIdentity` and
must match the adapter configuration exactly.

## Offline qualification matrix

All qualification uses fakes, fixtures, or deterministic local stubs. Network,
DNS, sockets, provider credentials, and live SDK behavior are prohibited.

| Case | Required proof |
|---|---|
| Valid completed output | One adapter call; real Phase 18B validation; completed output/audit; raw response absent. |
| Valid Phase 18C refusal | Zero adapter calls; existing refused audit. |
| Invalid-envelope mapping | One unchanged candidate, one real Phase 18B rejection, and `invalid_output`; no adapter validation. |
| Decoded scalar | Reaches real Phase 18B unchanged and is rejected once; no coercion. |
| Decoded array | Reaches real Phase 18B unchanged and is rejected once; no extraction or wrapping. |
| Decoded JSON `null` | Remains distinct from absence and is rejected once by real Phase 18B. |
| Absent candidate | Uses sanitized `provider_unavailable`; no sentinel, mapping, or envelope is fabricated. |
| Malformed JSON | Produces no candidate and follows sanitized `internal_unavailable`; raw bytes and decoder diagnostics are absent. |
| Decoder exception | Produces no candidate and follows sanitized `internal_unavailable` with no cause or context. |
| Timeout | One attempt; sanitized `ProviderTimeoutError`; no retry or exception chain. |
| Provider unavailable | One attempt; sanitized `ProviderUnavailableError`; no retry or exception chain. |
| Oversized request | Zero provider calls; fixed internal failure; request not retained. |
| Oversized response | One bounded attempt; response discarded; sanitized unavailable result. |
| Cost rejection | Zero adapter calls; existing `cost_limit` audit. |
| Hostile diagnostics | No raw diagnostic in exception, outcome, audit, capture, or test output. |
| Secret-like exception data | Value and derivatives absent from cause, context, output, audit, and captures. |
| Duplicate/unexpected call | Test fails unless exactly one call occurred. |
| Collision-bearing mapping | Candidate reaches the real Phase 18B validator and is rejected specifically for normalized-key collision. |
| Dependency boundary | Only the approved pinned dependency plus standard/frozen internal packages; no database, API, broker, execution, Railway, or unrelated runtime import. |
| Semantic-authority boundary | Both the static authority scan and the behavioral production-symbol instrumentation defined below are mandatory; either one failing or being incomplete fails qualification. The adapter may perform only trusted-request mapping, one provider operation where permitted, bounded decoding, and sanitized transport/failure translation. |
| Runtime-binding guard | Static import and construction scanning fails if a production runtime root imports, constructs, binds, configures, model-selects, feature-enables, or registers the adapter. Tests and the dedicated offline qualification harness may import it; production runtime entrypoints may not. |
| Retention boundary | No raw provider response, request, prompt, credential, or diagnostic survives in adapter/core public state. |
| Cleanup | All captures and process-local secret-bearing variables are cleared through success and failure boundaries. |

Tests must include a fake provider SDK or transport implementation whose imports
cannot initiate network access. Dependency scans must reject socket, generic HTTP,
database, subprocess, broker, execution, and unapproved provider packages outside
the single reviewed adapter boundary.

The minimum authoritative runtime-binding scan roots are `live/atlas/main.py`,
`live/atlas/api/`, `live/atlas/application/`, `live/atlas/services/`, and
`live/atlas/repositories/`, matching the existing runtime and Phase 18D guard
boundaries. Before implementation, the file list must be confirmed against every
additional module reachable from the production entrypoint; that final expanded
list is confirmed for Phase 18E as the named roots plus every Python module
reachable below those directories. The scan must detect imports, factory or
dependency-container registration, configuration-name access, model selection,
feature-flag enablement, and `ProviderPort` binding.

The static semantic-authority scan remains mandatory and fails if the adapter
imports, references, constructs, or calls `validate_output()`, input or output
projection, completed/refused/failed audit builders, citation resolution,
Snapshot verification or attestation, semantic policy, deterministic-state
enforcement, trusted `ValidatedAnalysisOutput` construction, or any equivalent
validation or audit authority. Passing this static scan alone is insufficient.

The behavioral authority test must patch or instrument the symbols as resolved
in the production consumer module, because `orchestrator.py` imports and binds
them directly. It must instrument all four exact module-bound symbols:

- `atlas_ai_orchestration.orchestrator.validate_output`;
- `atlas_ai_orchestration.orchestrator.completed_audit_from_validated_output`;
- `atlas_ai_orchestration.orchestrator.failed_audit`; and
- `atlas_ai_orchestration.orchestrator.refused_audit`.

Patching or instrumenting only the original SDK/source definitions is
insufficient. The test must fail if any of these four consumer-bound symbols is
omitted. It must also instrument the approved concrete adapter invocation method
and the actual concrete transport invocation point used by that adapter. The
approved symbols are
`atlas_ai_orchestration.openai_adapter.OpenAIProviderAdapter.invoke` and
`httpx.Client.send`. A fake-only helper
or non-production alias that the concrete adapter does not invoke cannot satisfy
this requirement.

For every applicable route, behavioral assertions must prove that:

- the concrete adapter invokes none of the four Phase 18D consumer-bound symbols
  and performs no equivalent direct SDK validation or audit construction;
- a candidate-producing route performs exactly one concrete transport operation,
  returns the decoded candidate without semantic normalization, repair,
  projection, coercion, wrapping, or fabrication, preserves object identity where
  the approved return contract permits it, and always preserves candidate value;
- Phase 18D invokes its module-bound `validate_output` exactly once for a returned
  candidate; zero or more than one invocation fails the test;
- successful validation invokes only
  `completed_audit_from_validated_output` exactly once;
- validation rejection invokes only `failed_audit` exactly once through the
  existing `invalid_output` route;
- Phase 18C refusal invokes only `refused_audit` exactly once and performs zero
  adapter and transport operations;
- a sanitized provider or adapter failure invokes only the Phase 18D audit builder
  established for its existing authoritative route, every non-applicable audit
  builder remains uninvoked, and the adapter constructs no audit; if that
  route-to-builder mapping is not settled by repository evidence, the reviewed
  implementation plan must name it from authoritative Phase 18D behavior before
  authorization rather than inventing a new route;
- absent candidate, malformed JSON, decoder rejection, decoder exception,
  timeout, provider unavailability, oversized response, and other no-candidate
  paths never invoke `validate_output` and never fabricate a candidate, sentinel,
  empty mapping, or envelope; they use only their approved sanitized Phase 18D
  failure route, with malformed JSON and decoder exceptions remaining
  `internal_unavailable` and absent candidates mapping to sanitized
  `provider_unavailable`;
- no-candidate and failure paths retain or expose no raw response, diagnostic,
  cause, context, or secret; and
- the actual concrete transport method is called exactly once on candidate-producing
  and post-transport failure paths, and zero times for Phase 18C refusal, cost
  rejection, invalid configuration, oversized request, and every other approved
  pre-transport rejection. No retry, fallback, alternate provider or model,
  continuation, or hidden second request is permitted.

The behavioral gate fails if it instruments only SDK definition sites, omits any
of the four consumer-bound Phase 18D symbols, omits the actual concrete adapter
or transport invocation point, substitutes a fake-only non-production path,
fails to prove route-specific audit-builder exclusivity, or fails to prove exact
validation and transport call counts.

## Feature-disable and rollback contract

- The concrete adapter is disabled by default.
- Missing, false, malformed, or conflicting enablement/configuration leaves the
  existing injected offline boundary in place and performs no provider call.
- Runtime code must not import or construct the adapter unless a later integration
  phase explicitly authorizes that wiring.
- Rollback is removal/disablement of the concrete adapter factory binding, returning
  to the existing injected `ProviderPort`; frozen contracts and Phase 18D remain
  unchanged.
- No fallback provider, alternate model, legacy provider path, or silent downgrade
  is permitted.
- Enabling or disabling the adapter grants no trading, strategy, risk, decision,
  broker, or execution authority.

## Offline implementation entry gates

Phase 18E offline implementation may begin when all gates pass:

1. Phase 18A through Phase 18D commits are present and the worktree is clean.
2. This definition passes independent read-only review.
3. One provider and official-SDK/minimal-HTTP decision is approved.
4. Python compatibility, exact dependency pin, and lock policy are approved.
5. Secret owner and configuration names are approved.
6. Request, response, timeout, token, and cost ceilings are resolved; the model
   identifier is an injected allowlisted value for offline tests only.
7. The decoded scalar/array/`null` return type, absent-candidate classification,
   and any `ProviderPort` type change are approved. Malformed JSON and decoder
   exceptions remain current-contract `internal_unavailable` unless a separate
   Phase 18D routing change is explicitly approved.
8. The production and test file boundary below is reviewed.
9. Implementation remains offline and requires no credential or network access.

## Exit gates

Phase 18E closes only when:

1. exactly one concrete adapter is implemented behind the reviewed port;
2. the adapter is default-disabled and has no runtime binding;
3. every qualification case passes offline with no skipped mandatory test;
4. all Phase 18A/B/C/D regressions remain unchanged and passing;
5. dependency, credential, secret-pattern, retention, and prohibited-capability
   scans pass;
6. Ruff and repository diff checks pass;
7. an independent read-only implementation review passes;
8. exactly one separate implementation commit is created; and
9. the result makes no deployment or operational-certification claim.

## Explicit non-goals

- real credentials or live provider qualification;
- networking in tests, retries, backoff, or fallback providers;
- persistence, PostgreSQL, HTTP/service APIs, or runtime integration;
- Railway, deployment, or operational observability integration;
- Phase 17E certification, R4, A5-U2Q, or operational enablement;
- trading, strategy, risk, decision, broker, or execution authority; and
- changes to the frozen Phase 18A contracts or Phase 18B validation authority.

## Offline implementation file boundary

The reviewed implementation set is limited to this document, the roadmap,
`live/requirements.txt`, the Phase 18D package models/ports/exports, the new
`live/atlas_ai_orchestration/openai_adapter.py`, the package-owned
`live/atlas_ai_orchestration/pricing_authority.py`, the Phase 18D dependency and
orchestration tests, and the new
`live/tests/test_openai_provider_adapter.py`. It must not modify Phase 18A
schemas, duplicate Phase 18B validation, or wire the adapter into an application
runtime.

## Operational enablement gate

Offline implementation completion and the Phase 3A pricing record do not by
themselves authorize construction in a runtime. A separately reviewed Phase 3
factory may use exactly `gpt-5.6-terra` only for the approved local manual
experiment. Production enablement remains blocked on model policy, OpenAI account
entitlement, retention controls, current pricing renewal, Security/Platform
secret ownership, and separate deployment approval. The identifier is not
represented as immutable.

The Phase 18E implementation and this definition must be reviewed together and
committed as one bounded Phase 18E set.

## Operational-gate evidence package (enablement remains closed)

This section is an evidence index, not an approval. It records only committed
design evidence and supplied bounded one-shot metadata. Unknown ownership,
external approval, current entitlement, and deployment decisions remain
blocking. See [the evidence index](PHASE_18E_EVIDENCE_INDEX.md),
[the operator checklist](PHASE_18E_OPERATOR_CHECKLIST.md),
[the go/no-go template](PHASE_18E_GO_NO_GO_TEMPLATE.md), and
[the rollback checklist](PHASE_18E_ROLLBACK_CHECKLIST.md).

| Gate | Status | Committed evidence | Missing artifact or decision | Responsible role | Acceptance criterion | Expiry/revalidation | Blocks enablement? |
|---|---|---|---|---|---|---|---|
| Secret ownership and custody | SATISFIED_BY_COMMITTED_EVIDENCE | Personal Project Owner approves Railway Variables as the future store, backend-service-only injection, 90-day rotation, incident-triggered rotation, one-hour revocation SLA, and no-value recording; committed runtime reads the key only for the adapter factory and tests/documentation prohibit leakage. | Actual Railway Variables configuration and service permissions remain a deployment-time check and are not inspected here. | Personal Project Owner | Documented custody design and committed service boundary are accepted; deployment verifies the named service and permissions without exposing a value. | Ownership, store, service, permission, or credential-process change. | No |
| Provider account entitlement | REQUIRES_OPERATOR_CONFIRMATION | Owner attests active billing and usable payment method/balance; one bounded transport reached the selected model at the recorded time. | Current model entitlement, rate limits, usage limits, and restriction status remain unverified. | Personal Project Owner / Provider Account Owner | Non-secret deployment-time check records pass/fail, timestamp, owner role, model, and sanitized limit suitability. | Account, model, project, billing, policy, access, or limit change. | Yes |
| Current pricing and renewal | SATISFIED_BY_COMMITTED_EVIDENCE | Owner is budget approver; supplied official prices are USD 2.00 input, USD 0.20 cached input, and USD 12.00 output per 1M tokens; application ceiling remains USD 0.12 per request. | None for this record; do not assume historical pricing remains current. | Personal Project Owner / Budget Owner | Pricing source and ceiling are recorded with renewal ownership. | Revalidate no later than 2026-09-05 and on model, tier, token-limit, caching, or official-price change. | No |
| Retention and data controls | SATISFIED_BY_COMMITTED_EVIDENCE | Dated owner acceptance covers applicable default provider retention up to 30 days, no-ZDR/no-regional-processing claims, `store:false`, no local raw cache, immediate raw-diagnostic deletion, bounded metadata retention up to 30 days, prohibited sensitive inputs, deletion/incident ownership, and revalidation triggers. | Actual provider policy state and deployment storage configuration remain operational checks; no provider or Railway system is inspected here. | Personal Project Owner / Security and Privacy Owner | Dated acceptance and committed request/diagnostic controls satisfy the documented personal advisory boundary. | Model, endpoint, API behavior, data policy, retention, storage, caching, or data-flow change. | No |
| Security and privacy review | SATISFIED_BY_COMMITTED_EVIDENCE | Owner self-review accepts committed least privilege, secret isolation boundary, untrusted-evidence/prompt-injection controls, sanitized logging, advisory-only behavior, and deterministic authority isolation. | None for the technical review; incident and credential-revocation procedure remains part of secret-custody follow-up. | Personal Project Owner / Security and Privacy Owner | Dated self-approval and risk acceptance references the committed controls. | Code, dependency, threat-model, data-flow, or policy change. | No |
| Deployment approval | REQUIRES_EXTERNAL_APPROVAL | Runtime documentation states no deployment or production enablement is authorized. | Approvers, target environment, change window, pre-deployment checks, and explicit go/no-go record. | Release/Platform owner | Recorded approval names target and rollback plan. | Any release, environment, or configuration change. | Yes |
| Rollback and kill switch | SATISFIED_BY_COMMITTED_EVIDENCE | Adapter is default-disabled; rollback is disablement/removal of the local factory binding; deterministic authority remains outside the adapter. | None for the documented offline boundary; production rollback rehearsal remains a later approval requirement. | Runtime owner | Disablement removes the binding and public behavior remains sanitized and deterministic. | Runtime binding or public-contract change. | No |
| Sanitized observability | SATISFIED_BY_COMMITTED_EVIDENCE | Personal Project Owner owns operations; committed `manual_ai_one_shot_diagnostic.v1` enforces bounded counters, fixed metadata, one-call coherence, pre-teardown capture, and content-free serialization. | Actual alert wiring and retention configuration remain deployment-time checks; no Railway or production system is inspected here. | Personal Project Owner / Operations and Observability Owner | Retain only permitted metadata for at most 30 days; alert on transport/rejection/count/cost/teardown/authority violations using USD 0.10 warning and USD 0.12 hard ceiling; public contracts remain unchanged. | Schema, alert, retention, cost, ownership, or authority-boundary change. | No |

### Successful controlled one-shot metadata

The supplied result is retained here without provider content:

| Field | Value |
|---|---|
| Schema version | `manual_ai_one_shot_diagnostic.v1` |
| HEAD | `f125f94ec7e2897035333749687b2c39148f27a4` |
| Exit code | `0` |
| Public result | `completed` |
| Provider transport count | `1` |
| Authoritative fields validated | `11` |
| Failure counters | all `0` |
| Phase 18B rule counters | all `0` |
| Semantic subreason counters | all `0` |
| Deterministic authority unchanged | `true` |
| Snapshot before teardown | `true` |

No prompt, payload, response, evidence, header, request ID, credential, or raw
diagnostic is preserved. This metadata is qualification evidence only and does
not authorize provider activation, deployment, or trading.

## Personal-owner decision record

Record date: 2026-08-06.

The operator states that this is a single-owner personal project for personal
use, not a company, employer, client, team, or external-user service. The
Personal Project Owner personally holds the provider-account, budget,
security/privacy, deployment, release, and operations roles. This attestation
records role ownership only; it does not record a name, account identifier, or
secret.

The owner accepts the following bounded risks and controls: no intentional
submission of credentials, brokerage credentials, personal identifiers, or
unnecessary sensitive data; no local raw prompt/response retention; only fixed
schema metadata and bounded counters may be retained; provider data is not used
for model training by default unless explicitly opted into; abuse-monitoring and
Responses API application-state retention may each be up to 30 days by default;
and Zero Data Retention is not claimed or enabled by this evidence.

The owner self-approves the committed security/privacy controls and accepts that
the AI remains advisory-only. Deterministic code remains the sole authority for
entries, exits, sizing, risk, orders, and execution. This is not a deployment or
production go/no-go approval.

Pricing evidence supplied for this record identifies `gpt-5.6-terra` standard
prices as USD 2.00 per 1M input tokens, USD 0.20 per 1M cached-input tokens, and
USD 12.00 per 1M output tokens, sourced to
<https://developers.openai.com/api/docs/models/gpt-5.6-terra>. The application
ceiling remains USD 0.12 per request. Pricing must be revalidated by
2026-09-05 and whenever model, tier, token limits, caching behavior, or official
pricing changes.

The committed adapter sends `store: false` and the adapter test asserts that
field; this proves request construction only. It does not prove Zero Data
Retention, regional processing, or any provider-side retention override.

## Retention acceptance and billing attestation

Record date: 2026-08-06.

The Personal Project Owner self-approves the applicable default provider
retention, which may be up to 30 days. Zero Data Retention, regional processing,
and provider-side retention overrides are not claimed. `store: false` remains
mandatory and is proven by the committed adapter and test; no local cache of
provider prompts or responses is created or retained. Raw local provider
diagnostics are deleted immediately after an authorized bounded operation. Only
the already-approved sanitized counters and schema metadata may be retained,
for no more than 30 days.

The owner will not intentionally submit credentials, brokerage secrets, account
identifiers, personal identifiers, or unnecessary sensitive information. The
owner is the deletion and incident-response owner. On suspected exposure, the
adapter remains or returns disabled, the credential is revoked within one hour,
deletable local raw diagnostic data is removed, and only a sanitized incident
record without provider content or secrets is created. This acceptance must be
revalidated whenever the model, endpoint, API behavior, provider data policy,
retention settings, storage/caching behavior, or application data flow changes.

Billing attestation: “The Personal Project Owner attests that API billing is
active and a valid payment method or usable balance is available.” This records
no payment, balance, billing-account, organization, project, or account
identifier. Active billing confirms neither continuing model entitlement nor
current rate or usage limits. The prior one-shot transport is historical access
evidence only.

The smallest non-secret entitlement check before any future go/no-go is to record
pass/fail, verification timestamp, verifying owner role, model name
`gpt-5.6-terra`, and sanitized limit suitability for the approved manual
operation: model access, sufficient rate limits, usage limits compatible with
the approved budget and USD 0.12 request ceiling, and no billing suspension or
account restriction. No account identifiers, balances, payment details,
credentials, headers, request IDs, or raw dashboard content may be recorded.

## Railway custody and observability decisions

The Personal Project Owner approves Railway Variables as the future runtime
secret location. The credential is to be injected only into the backend service
that owns and executes the AI adapter. It must never be stored in Git,
repository files, documentation, application output, diagnostic artifacts, or
logs. The owner holds secret, rotation, revocation, operations, and observability
responsibility. Routine rotation is every 90 days; immediate rotation is
required after suspected exposure, unauthorized access, relevant permission
change, or compromise of the Railway project, service, or account. Maximum
revocation SLA after discovery or reasonable suspicion is one hour. Temporary
PowerShell handling used for the bounded smoke is not the production solution.

This is an approved future design, not proof that Railway Variables are
currently configured. No Railway account, project, service identifier, variable
name beyond the committed configuration contract, permission state, or secret
value is recorded. Deployment-time verification must confirm the backend service
scope and permissions without printing or retrieving the value.

The Personal Project Owner owns sanitized observability. Retention is limited to
30 days for schema/version metadata, timestamps, result category, bounded
counters, validation totals, deterministic-authority flags, and teardown/snapshot
lifecycle flags already allowed by `manual_ai_one_shot_diagnostic.v1`. Credentials,
prompts, responses, payloads, evidence, headers, authorization values, provider
request IDs, account identifiers, and raw diagnostics are forbidden.

Alerts are required for any provider transport failure; any validation, contract,
citation, semantic, numeric, authority, or binding rejection; transport count
above the operation's authorized count; estimated cost greater than or equal to
USD 0.10; failure to collect the snapshot before teardown; and any evidence that
deterministic authority changed or the AI path attempted to influence entries,
exits, sizing, risk, orders, or execution. USD 0.12 remains the hard application
ceiling. Alert wiring and actual retention configuration are deployment-time
checks, not evidence supplied by this documentation task.

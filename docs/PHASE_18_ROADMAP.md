# Phase 18 AI Analysis Roadmap

Status: Phase 18A, Phase 18B, Phase 18C, and Phase 18D are complete. This
document authoritatively orders Phase 18E as the next work package, subject to
the operational gates in `PHASE_18E_PROVIDER_ADAPTER.md`. It does not
authorize provider access, deployment, persistence, an API, Railway work, R4,
or operational certification.

## Completed foundations

- **Phase 18A — Frozen AI Analysis Contract v1.** The closed
  `ai_analysis_input.v1`, `ai_analysis_output.v1`, and
  `ai_analysis_audit.v1` schemas and `ai_analysis_policy.v1` are immutable.
- **Phase 18B — Deterministic contract SDK.** `atlas_ai_analysis` owns input
  projection, output validation, citation and authority enforcement, and the
  completed, refused, and failed audit builders.
- **Phase 18C — Offline evidence orchestration.** `atlas_ai_service` retrieves
  bounded canonical Snapshot evidence through an injected port, verifies it
  through `atlas_snapshot`, constructs the typed `SnapshotVerification`
  attestation, and returns `EligibleAnalysis`, `RefusedAnalysis`, or a sanitized
  pre-eligibility `ServiceFailure`.

## Phase 18D — Offline Provider Orchestration Core

### Objective

Build a pure orchestration core that accepts a Phase 18C outcome, constructs a
deterministic trusted provider request for eligible evidence, invokes only an
injected provider port, validates provider output exclusively through Phase 18B,
and returns a sanitized output/audit result. Local tests remain fully offline.

Phase 18D is locally implementable without Phase 17 operational certification,
A5-U2Q, R4, Railway, PostgreSQL, or a live provider. Those systems may become
dependencies of later adapter, persistence, deployment, or operational phases;
they are not dependencies of this core.

### Responsibilities

Phase 18D owns:

1. routing the three Phase 18C outcomes without weakening their meaning;
2. constructing a deterministic trusted request for eligible analysis;
3. enforcing a trusted pre-call cost limit before provider invocation;
4. invoking one injected provider port at most once;
5. classifying typed provider failures without retaining raw diagnostics;
6. passing every provider-produced output candidate to Phase 18B
   `validate_output()` exactly once as the sole output-validation authority and
   routing only from its immutable `ValidatedAnalysisOutput` result;
7. constructing the existing Phase 18B completed, refused, or failed audit when
   the frozen audit schema can represent the outcome; and
8. returning deterministic sanitized value types suitable for a later
   persistence or API layer.

Phase 18D does not recompute Snapshot evidence, derive evidence digests, project
analysis input, reimplement citation validation, inspect deterministic state
independently, or broaden any frozen allowlist.

### Explicit non-goals

- concrete model/provider adapters or SDKs;
- network or tool access;
- provider credentials or configuration;
- retries, backoff, failover, or distributed idempotency;
- persistence or atomic output/audit storage;
- PostgreSQL or any other database;
- HTTP, service, browser, or streaming APIs;
- prompt or provider payload logging;
- deployment, Railway, R4, or operational certification;
- changes to a frozen Phase 18A schema or policy; and
- order, strategy, risk, decision, broker, or execution authority.

## Typed input routing

The Phase 18D entry point accepts the Phase 18C `EvaluationOutcome` union.

| Input | Provider call | Required result |
|---|---:|---|
| `EligibleAnalysis` | permitted once | Continue through cost, prompt, provider, validation, and audit flow. |
| `RefusedAnalysis` | prohibited | Construct `refused_audit()` using an injected audit identity and clock-derived timestamp; return no prompt, provider request, or output. |
| Phase 18C `ServiceFailure` | prohibited | Return a deterministic sanitized pre-eligibility service outcome without an audit. |

`ai_analysis_audit.v1` cannot represent the pre-eligibility service failure:
`failed_audit()` requires an `EligibleAnalysis`, while `refused_audit()` permits
only the frozen Snapshot refusal reasons. Phase 18D must not fabricate an input,
digest, refusal reason, or audit to bridge this gap. A future contract version
would be required to persist such an event as an AI analysis audit.

## Trusted prompt and provider ports

### Trusted prompt builder

An injected trusted-prompt abstraction receives only the frozen
`EligibleAnalysis.analysis_input` and returns an immutable provider request value.
Its implementation must be deterministic for identical input and configuration.

The trusted request must:

- separate trusted instructions from evidence values;
- delimit every evidence string as untrusted data;
- state the allowlisted purpose and required `ai_analysis_output.v1` shape;
- prohibit tools, external retrieval, authority claims, deterministic-state
  replacement, uncited claims, and invented numeric content; and
- contain no credentials, endpoints, provider configuration, canonical Snapshot
  wrapper, operational metadata, or audit metadata.

The builder may not return a raw loggable prompt string as evidence. Phase 18D
must not expose or retain the trusted request in its public outcome or audit.

### Provider port

An injected provider port accepts the immutable trusted request and returns one
untrusted output candidate. It may instead raise only reviewed typed failures
that the core can classify, including timeout and provider unavailability.

The port boundary does not grant the core network access. Concrete adapters own
transport, authentication, endpoint selection, timeout enforcement, and provider
SDK details in a later work package. Raw adapter exceptions and response payloads
must not cross the port.

## Identity and time authority

The orchestration core receives injected factories for analysis-output and
analysis-audit UUIDv7 identities plus an injected UTC clock. It never reads wall
clock time or generates random identifiers implicitly. Factories must return
values accepted by the frozen Phase 18B validators; invalid factory output fails
closed as `internal_unavailable` without a provider retry.

Generator identity is a non-secret injected `GeneratorIdentity`. It contains
only the frozen provider and model identifiers and never credentials, endpoints,
pricing configuration, or provider options.

## Cost, timeout, and retry behavior

- A trusted injected cost policy evaluates the bounded request before invocation.
- Rejection prevents the provider call and produces `failed_audit(...,
  reason="cost_limit")`.
- The core performs no retry under any condition.
- Concrete adapters enforce timeouts. A reviewed typed timeout maps to
  `provider_timeout`; typed unavailability maps to `provider_unavailable`.
- Unexpected provider-port failures map to `internal_unavailable`.
- Raw exception text, cause, context, provider payload, and timing diagnostics are
  discarded before constructing a public outcome.

## Provider output and audit flow

Provider output is untrusted. Phase 18D must not coerce, repair, partially accept,
or supplement it.

1. Pass the candidate to Phase 18B `validate_output(candidate, eligible)`, which
   returns an immutable `ValidatedAnalysisOutput` after copying and freezing the
   fully validated value. Supported public APIs cannot construct this type from
   unchecked data; this is an application boundary, not protection against
   hostile same-process reflection into private Python internals.
2. If the trusted validated status is `available`, construct
   `completed_audit_from_validated_output()` without revalidation and return the
   validated output plus audit.
3. If the validated status is `unavailable`, map its approved
   `unavailable_reason` to `failed_audit()`. Do not represent it as completed and
   do not return or retain the unavailable provider payload as evidence.
4. Map every exception raised by Phase 18B output validation to
   `invalid_output`. The frozen SDK's exception classes do not expose a stable,
   machine-readable distinction between every contradiction, recomputation, and
   prohibited-authority failure. Phase 18D must not parse exception messages to
   infer a narrower reason. Specific approved failure reasons such as
   `missing_citation`, `deterministic_state_contradiction`, and
   `prohibited_content` remain usable when they arrive in a structurally valid
   `status="unavailable"` output that passes `validate_output()`.
5. Never emit fallback prose or an unvalidated output.

Every audit is constructed only by the existing Phase 18B builders. Phase 18D
does not construct audit mappings directly.

## Deterministic sanitized outcomes

Public Phase 18D outcomes may contain only the validated available output and its
completed audit, a refused audit, a failed audit with its approved reason, or a
fixed sanitized pre-eligibility service result.

They must not contain:

- canonical Snapshot evidence or derived prompt content;
- provider request or raw provider response;
- malformed output payloads;
- credentials, endpoints, headers, or provider configuration;
- raw exception messages, causes, contexts, tracebacks, or diagnostics;
- cost calculations or secret pricing inputs; or
- database, infrastructure, execution, or operational metadata.

No Phase 18D result grants trading, strategy, risk, decision, or execution
authority.

## Local acceptance-test matrix

All tests use fakes and deterministic injected factories. They must not import or
contact a provider SDK, network client, database client, broker, Railway, or live
service.

| Case | Required assertions |
|---|---|
| Eligible, valid available output | One prompt build, one provider call, one Phase 18B validation, completed audit, matching frozen identities. |
| Refused analysis | Zero prompt/provider calls; existing refused audit only. |
| Pre-eligibility service failure | Zero prompt/provider calls; sanitized result; no audit. |
| Pre-call cost rejection | Zero provider calls; `cost_limit` failed audit. |
| Typed timeout | One provider attempt; no retry; `provider_timeout` failed audit. |
| Typed unavailability | One provider attempt; no retry; `provider_unavailable` failed audit. |
| Unexpected provider failure | One attempt; sanitized `internal_unavailable`; no raw exception cause or context. |
| Valid unavailable output | Phase 18B validation occurs; failed audit uses approved reason; payload is not returned. |
| Malformed/unknown-version output | Phase 18B rejection; `invalid_output`; no payload retained. |
| Missing citation in an invalid available output | Phase 18B rejection; deterministic `invalid_output`; no fallback narrative or exception-text parsing. |
| Contradiction or recomputation in an invalid available output | Phase 18B rejection; deterministic `invalid_output`; no exception-text parsing. |
| Prohibited authority/content in an invalid available output | Phase 18B rejection; deterministic `invalid_output`; no exception-text parsing. |
| Valid unavailable output with a specific approved reason | Phase 18B validation succeeds; failed audit preserves that approved reason. |
| Invalid injected ID/time | Fail closed without retry or unvalidated audit. |
| Delayed evidence | Available output must retain the frozen `delayed_evidence` limitation requirement. |
| Prompt-injection-like evidence | Evidence remains delimited data and cannot modify instructions, tools, purpose, or output schema. |
| Dependency/purity scan | No concrete provider, HTTP, database, broker, execution, persistence, or runtime API dependency. |
| Redaction scan | No prompt, payload, credential-like value, endpoint, or raw diagnostic enters outcomes or audits. |

The Phase 18A specification tests, Phase 18B SDK tests, Phase 18C tests, and the
new focused Phase 18D tests must all pass together. Ruff and repository diff
checks must pass.

## Phase 18E — Offline Concrete Provider Adapter Contract and Qualification Harness

Phase 18E is the next ordered Phase 18 work package. Its purpose is to place
exactly one concrete provider adapter behind the existing Phase 18D
`ProviderPort` and qualify the adapter entirely offline. The authoritative
design, entry blockers, security boundary, qualification matrix, and exit gates
are defined in `PHASE_18E_PROVIDER_ADAPTER.md`.

Phase 18E offline implementation is authorized for an OpenAI direct-HTTP adapter
using `httpx==0.28.1`, an injected explicit model allowlist, and the approved
bounded policy in `PHASE_18E_PROVIDER_ADAPTER.md`. It remains default-disabled,
offline-qualified, and unattached. Operational enablement is separately blocked
until an immutable model identifier, account entitlement, retention/ZDR,
pricing metadata, secret ownership, and runtime binding are independently
verified. The implementation authorizes no credential, provider call, runtime
integration, deployment, or operational certification.

## Later work-package boundaries

After Phase 18E, later explicitly approved phases may define:

1. persistence ports and atomic storage of validated output/audit records;
2. service or HTTP APIs, authorization, request idempotency, and concurrency;
3. deployment configuration and operational observability with sanitized logs;
4. operational certification and rollback procedures.

Those phases must preserve the Phase 18A contracts and Phase 18B validation
authority. Local Phase 18E completion is engineering evidence only and is not an
operational certification claim.

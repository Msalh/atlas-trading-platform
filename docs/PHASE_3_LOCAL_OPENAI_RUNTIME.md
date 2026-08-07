# Phase 3 — Default-disabled local OpenAI runtime binding

Status: implemented for offline review only. No live provider request, deployment,
production enablement, persistence, background processing, or trading authority is
included.

## Scope

The runtime factory may attach one `ManualAIExplanationService` only at
`app.state.manual_ai_explanation_service`. That state member is consumed solely by
the existing manual `POST /api/v1/trader-now/manual-advisory` dependency. It is
created during application lifespan only in `development` when every server-side
configuration and pricing gate passes, and it is removed during shutdown.

Imports and default startup construct no provider. Missing, false, whitespace-
modified, case-modified, or otherwise malformed enablement leaves the state member
absent. Factory rejection has the same result. The public route therefore retains
its existing sanitized `unavailable` / `analysis_unavailable` response.

## Server-side configuration

No values are committed. Every enabled-mode value is mandatory:

| Name | Requirement |
|---|---|
| `ATLAS_AI_PROVIDER_ENABLED` | Exactly the case-sensitive value `true` in `ENVIRONMENT=development`; every other value or environment is disabled. |
| `ATLAS_AI_PROVIDER_API_KEY` | Non-empty server-only credential; not read while disabled. |
| `ATLAS_AI_PROVIDER_MODEL` | Exactly `gpt-5.6-terra`; no override or fallback. |
| `ATLAS_AI_PROVIDER_TIMEOUT_SECONDS` | Positive, finite, and no greater than 60. |
| `ATLAS_AI_PROVIDER_MAX_REQUEST_BYTES` | Positive integer, no greater than 65,536. |
| `ATLAS_AI_PROVIDER_MAX_RESPONSE_BYTES` | Positive integer, no greater than 131,072. |
| `ATLAS_AI_PROVIDER_MAX_OUTPUT_TOKENS` | Positive integer, no greater than 4,096. |
| `ATLAS_AI_PROVIDER_MAX_ESTIMATED_COST` | At least the authoritative USD 0.081920 maximum and no greater than USD 0.12. |

The fixed pricing identity is `openai` / `gpt-5.6-terra` / `default`, reference
`openai-gpt-5.6-terra-default-2026-08-06`. Construction fails before provider
creation when the authority cannot resolve that exact record. The adapter resolves
the same authority again before credential access or transport on every manual
invocation. The record expires at `2026-09-05T00:00:00Z`; no fallback price exists.

## Provider and evidence boundary

The factory composes the existing Phase 18C evidence service, Phase 18D provider
orchestrator, Phase 18B validator/audit authority, deterministic trusted prompt,
and `OpenAIProviderAdapter`. It does not change those contracts. Provider identity
is fixed to `openai` / `gpt-5.6-terra` and must match the orchestrator generator.

The adapter performs one non-streaming Responses API operation only after the
manual route has composed and validated the existing MNQ / 5m /
`displacement_volume_context` evidence. Every prepared request explicitly contains
`store: false`, `stream: false`, the fixed model, bounded output tokens, trusted
instructions, and only the validated evidence projection. No browser prompt,
provider selection, model selection, credential, policy input, tool, retrieval,
previous response, background mode, or persistence option is accepted.

`store: false` is the approved local experiment control; it is not represented as
Zero Data Retention. Ordinary provider data-control and retention policies may
still apply. Production enablement remains separately prohibited.

The AI output can contribute only the Phase 18B-validated explanation summary,
claims, citations, and limitations. Deterministic Buy/Sell/No Trade, Entry, Stop
Loss, Take Profit, confidence, and all trading state remain authoritative and are
not writable by this binding.

## Failure and rollback

Missing or malformed configuration, missing credentials, unresolved or expired
pricing, cost rejection, timeout, provider failure, malformed output, or Phase 18B
rejection produces only the existing sanitized unavailable explanation. No failure
reason identifies credentials, pricing, entitlement, provider diagnostics, or
internal validation to the browser.

Rollback is the exact disablement or removal of this factory binding. It requires
no schema, database, persisted data, scheduler, worker, broker, alert, or trading
change.

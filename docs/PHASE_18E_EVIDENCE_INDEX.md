# Phase 18E Operational-Gate Evidence Index

Status: preparation only. Phase 18E remains closed.

| Evidence | Authoritative reference | Scope and limitation |
|---|---|---|
| Frozen contracts and Phase 18B authority | [Phase 18 roadmap](PHASE_18_ROADMAP.md) | Establishes immutable schemas and deterministic validation; grants no provider or trading authority. |
| Adapter contract and offline qualification | [Phase 18E adapter definition](PHASE_18E_PROVIDER_ADAPTER.md) | Documents one adapter, bounded transport, no retries, default-disabled operation, and open operational gates. |
| Local runtime boundary | [Phase 3 local runtime](PHASE_3_LOCAL_OPENAI_RUNTIME.md) | Manual-only, development-only, default-disabled binding; no production authorization. |
| Persistence boundary | [Phase 18F persistence](PHASE_18F_PERSISTENCE.md), [Phase 18H-1 wiring](PHASE_18H_RUNTIME_WIRING.md) | Offline contracts/candidate wiring only; no production database or runtime enablement. |
| One-shot observability | `live/atlas/manual_ai_smoke.py` and its committed tests | Fixed bounded report, one attempt, pre-teardown snapshot; no content retention. |
| Controlled success metadata | Phase 18E adapter document’s metadata table | Supplied counters and metadata only; not a production certification or approval. |
| Personal-owner decisions | Phase 18E adapter document’s personal-owner record | Owner role attestation and risk acceptance; does not replace missing technical custody, entitlement-limit, data-control, observability, or deployment decisions. |
| Official model pricing | <https://developers.openai.com/api/docs/models/gpt-5.6-terra> | Supplied current price facts only; revalidation remains due by 2026-09-05. |
| Provider data controls | <https://developers.openai.com/api/docs/guides/your-data> | Supplied default training/retention facts; ZDR is not claimed. |

The status matrix and unresolved decisions are maintained in
[PHASE_18E_PROVIDER_ADAPTER.md](PHASE_18E_PROVIDER_ADAPTER.md), which is the
single operational-gate source of truth.

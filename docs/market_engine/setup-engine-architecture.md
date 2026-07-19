# Setup Engine — Architecture

**Status: foundation approved and implemented (Sprint 17B, 2026-07-19); first real setup approved
and implemented (Sprint 18, 2026-07-19). Persisted here for the first time — this design existed
only as chat content across Sprint 17's planning, 17B's foundation, and 17B's five accepted
refinements until now.** Extends `rule-engine-architecture.md` and `roadmap.md`'s Phase 3 entry;
does not repeat their reasoning.

## Position in the pipeline

**Corrected 2026-07-19** — an earlier version of this section showed a single linear chain ending
`→ LLM → Execution`, which wrongly implied the LLM sits in the decision path. It does not. There
are two separate paths sharing one common prefix, and they must not be drawn as one:

**Deterministic decision path** (what Strategy, Paper Trading, and Live Execution consume):

```
Market Engine → Rule Engine → Setup Engine → Strategy & Signal Layer → Paper Trading → Live Execution
```

**Interpretation path** (a side branch off Setup Engine, not a continuation of the decision path):

```
Setup Engine → LLM narration/interpretation
```

Strategy & Signal Layer (Phase 4, not yet designed) consumes deterministic Setup Engine output —
never LLM output. The LLM consumes Setup Engine output for narration/interpretation only; nothing
downstream of it feeds back into the decision path. This is Architecture Principles' AI Boundaries
rule applied at this specific junction: decisions must be reproducible and auditable, which only
the deterministic side can promise (see `rule-engine-architecture.md`'s §4 for the fuller
statement of this same rule, applied to Rule Engine/Setup Engine vs. the LLM generally).

Setup Engine itself consumes `RuleEngineOutput` only — never `MarketState`, never any Market
Engine read port directly (checkable by grep: `atlas/setup_engine/` must never import
`atlas.market_engine`). It is deterministic, code-defined composition of Rule Engine facts into
higher-level market structures — still never an LLM call, still never a probability. The future
LLM consumes Setup Engine's output only, never Rule Engine's directly — see
`rule-engine-architecture.md`'s §3 for the full corrected interface statement.

## Package layout

`atlas/setup_engine/`:
- `models.py` — `SetupFamily`, `Severity`, `SupportingFact`, `SetupEvidence`, `SetupDefinition`,
  `SetupResult`, `InsufficientData`, `SetupOutcome`, `SetupEngineOutput`, `SetupEvaluationContext`.
- `evidence.py` — `supporting_fact_from_rule_engine_output()`, a shared construction helper so a
  setup's `fact_name`/`occurred_at`/`value` are always copied consistently from a
  `RuleEngineOutput`.
- `registry.py` — `SetupRegistration`, `REGISTRY`, `validate_registry`, `required_history`.
- `setups/` — one module per real setup (created in Sprint 18, when the first real setup existed
  to put in it — not created speculatively in 17B). No family-level subdirectory split yet; that
  is deferred until enough real setups within one family justify it, the same "don't build
  structure ahead of real need" reasoning `atlas/monitoring.py` already established for itself.
- `service.py` — `evaluate_registration()`, `build_setup_engine_output()`,
  `setup_engine_output_to_dict()`.

## Domain model

- **`SetupFamily`** — closed `str` enum, deliberately: `ICT`, `WYCKOFF`, `ORDER_FLOW`,
  `AUCTION_MARKET_THEORY`, `MOMENTUM` (added Sprint 18 — see that Sprint's entry in
  `setup-inventory.md` for why `ORDER_FLOW` would have been the wrong classification for a setup
  using no bid/ask, delta, footprint, imbalance, or absorption data), `CONFLUENCE` (added Sprint
  23A — see `setup-engine-catalog.md`'s CONFLUENCE section for the classification precedence and
  anti-dumping-ground rule this member exists under). Extended deliberately, the same discipline
  `Timeframe` already established — a setup with a genuinely poor fit should extend this enum, not
  be forced into the nearest imperfect family. `MEAN_REVERSION` is catalog-only as of Sprint 23A —
  proposed in planning (`setup-engine-catalog.md`) but not yet added to this enum, since no setup
  has been implemented under it; it gets added the same deliberate way when one actually is.
- **`Severity`** — closed `str` enum: `WEAK`, `NORMAL`, `STRONG`. Deliberately not a float
  confidence score — an enum cannot be averaged, thresholded with `>`, or mistaken for a
  statistical score. Optional on `SetupResult`; structurally forbidden to be non-`None` when
  `detected=False` (enforced in `SetupResult.__post_init__`, not just documented).
- **`SupportingFact`** — one Rule Engine fact's contribution to a setup's evidence:
  `fact_name`, `occurred_at`, `value`, and `detail: Mapping[str, int|float|str|bool]` — bounded to
  the same scalar-only constraint `FactDefinition.params` already uses, not a fully open
  `dict[str, Any]`. This is a deliberate, load-bearing choice: it is what makes Setup Engine's
  evidence a consistent contract for whatever eventually consumes it (the future LLM, first),
  rather than each setup inventing its own shape.
- **`SetupEvidence`** — `supporting_facts: tuple[SupportingFact, ...]`, in the order the setup's
  own logic consulted them.
- **`SetupDefinition`** — Setup Engine's analog of `FactDefinition`: `name`, `version`, `family`,
  `params`. Same `MappingProxyType` immutability normalization.
- **`SetupResult`** — `setup_name`, `definition_version`, `detected`, `severity`, `evidence`.
- **`InsufficientData`** — `setup_name`, `definition_version`, `reason`. A distinct type from
  `atlas.rule_engine.models.InsufficientData`, not a reuse of it — reuse would leave the identifier
  field misleadingly named `fact_name` for what it actually identifies here.
- **`SetupEngineOutput`** — `schema_version`, `symbol`, `timeframe`, `occurred_at`,
  `setups: tuple[SetupOutcome, ...]`. **Ordered tuple, not a dict keyed by name** — every
  `SetupOutcome` already carries its own `setup_name`, so a dict key would only duplicate that
  value; keeping the canonical container ordered end-to-end (construction through serialization)
  means the in-memory contract and the JSON contract are identical in shape, with no
  dict-to-list transformation step. Order is registry order (Sprint 14's own "registry tuple order
  provides deterministic output ordering" rule, reused here).
- **`SetupEvaluationContext`** — `history: list[RuleEngineOutput]` (ascending, current bar last,
  the same window convention used everywhere in this codebase), plus a `current` property derived
  as `history[-1]` — never a second, independently-set field, so it can never disagree with
  `history[-1]`. Rejects an empty `history` in `__post_init__` (defense in depth — the intended
  construction path, `build_rule_engine_output_window`, already refuses an empty input).

## Registry

`SetupRegistration(name, evaluate, definition, history_param=None, required_facts=())`.
`history_param` names which key in `definition.params` supplies required history depth (`None` →
`1`), following the exact discipline `FactRegistration.window_param` already established: never a
second, independently-set copy of a derivable value. `required_facts` names which Rule Engine fact
names a setup's `evaluate()` reads, cross-validated against Rule Engine's own `REGISTRY` by
`validate_registry` — a setup naming a fact Rule Engine doesn't actually compute fails validation
at the point the registry is assembled, not silently at evaluation time.

`REGISTRY` **may be empty** — a deliberate divergence from Rule Engine's own `validate_registry`,
which requires non-empty. That rule was written in Sprint 14, after six real facts already
existed; Setup Engine's registry was introduced at the foundation stage (17B) before any real
setup existed. An empty registry honestly represented "the machinery exists, nothing is registered
yet" rather than needing a synthetic placeholder entry that would risk being forgotten once real
setups arrived. `required_history(registry=REGISTRY)` defaults to `1` for an empty registry
(`max(..., default=1)`) for the same reason.

## Orchestration

`evaluate_registration(context, registration) -> SetupOutcome` is the single per-registration
evaluation point — `build_setup_engine_output` always calls through it, never `registration.evaluate`
directly, so future profiling/tracing has exactly one hook without restructuring this module.
`build_setup_engine_output(context, registry=REGISTRY) -> SetupEngineOutput` is pure and
synchronous: the full `context` is passed to every registration's `evaluate` uniformly; each
setup's own logic decides how much of `context.history` it actually uses (the orchestrator never
truncates per-registration), the same convention Rule Engine facts already follow relative to
their own window.

## Serialization

`setup_engine_output_to_dict()` mirrors `rule_engine_output_to_dict()`'s posture exactly: pure
domain serialization, zero FastAPI/HTTP knowledge. `setups` walks the already-ordered tuple
directly — no dict-to-list transformation, unlike Rule Engine's own `facts` dict. Every value
involved (`SupportingFact.detail`'s bounded mapping, `Severity`'s string enum) is already
JSON-native by construction, proven by a `json.dumps()` test, not assumed.

## Statelessness and replay

Inherited "for free" from purity, the same as Rule Engine: given the same `SetupEvaluationContext`
and the same registry, `build_setup_engine_output` always returns the same `SetupEngineOutput`,
regardless of whether the underlying `MarketState` window came from live ingestion or replay.

## Setups

See `setup-inventory.md` for the catalog of implemented setups and their exact definitions.

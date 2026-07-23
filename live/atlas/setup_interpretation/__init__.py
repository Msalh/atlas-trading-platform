"""
Setup Interpretation - a new top-level sibling package providing one
canonical interpretation layer between Setup Engine and Strategy Engine,
without modifying any frozen computation. See docs/adr (a future ADR, not
yet written) and the approved Phase N3 architecture review for the full
rationale: Setup Engine's own SetupResult deliberately never asserts a
direction (some setups have none by design - e.g.
vwap_extension_with_volume_confirmation's explicit "interpretation-neutral"
stance - others simply lack directional evidence), and letting every
future StrategyPlugin independently re-derive "what direction does this
setup imply" from raw Rule Engine facts would gradually turn Strategy
Engine into an uncoordinated second Rule Engine consumer. This package
exists to give exactly one, versioned, auditable answer instead.

Sprint 1 scope only: models.py (SetupDirection, DirectionSource,
SetupInterpretation), definitions.py (the versioned canonical
interpretation ruleset, SETUP_INTERPRETATION_V1), and fingerprint.py (a
self-contained canonical-hashing helper, not imported from
market_context.fingerprint). No service.py, no interpretation logic, no
wiring into ReplayFrame yet - those are later, separately-approved steps.

Never recomputes MarketState, Rule Engine facts, or Setup Engine setups.
Interpretation may only ever consume already-computed RuleEngineOutput and
SetupEngineOutput (Sprint 2's own concern - Sprint 1 defines the domain
model and canonical rules those functions will apply, nothing more).

Depends only on atlas.core.primitives (where genuinely needed) and the
Python standard library - never atlas.rule_engine, atlas.setup_engine,
atlas.replay_engine, atlas.market_context, atlas.strategy_engine,
repositories, the API, events, research, execution, brokers, or LLM
services. definitions.py identifies setups by their stable string name
(e.g. "displacement_with_volume_confirmation"), never by importing
Setup Engine's own frozen SETUP_ENGINE_REGISTRY.
"""

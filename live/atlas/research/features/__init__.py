"""
Phase N4 Sprint 4 (Feature Registry). Turns a raw MarketState window into a
named, versioned, deterministic scalar - nothing more. Answers exactly one
question: "what is the value of this defined quantity, for this window,
right now?" Never whether that value is interesting, correlates with
anything, or supports any claim - those are Discovery Engine's (Sprint 10)
and Hypothesis's (Sprint 1, operationally Sprint 5+) jobs respectively. See
this package's own frozen boundary review (Sprint 3->4 transition): Feature
Registry must never create a Finding or Hypothesis, compare Experiments,
access the Ledger, perform similarity search, ranking, validation, AI
reasoning, or statistical judgment.

Two tiers, per docs/phase-n4-research-engine-blueprint.md's own Feature
entity: Registered (code-defined, reviewed, permanent - registry.py,
structurally mirroring atlas.rule_engine.registry's FactRegistration/
REGISTRY shape) and Candidate (declarative, closed-vocabulary specs
interpreted by one fixed evaluator - candidate.py - never dynamically
generated or executed code, the feature-generation-safety extension of
Design Principle VIII.1).

Depends on exactly one production package: atlas.market_engine.models
(MarketState), read-only. Rule Engine's own models are never imported -
"mirroring the shape" (the roadmap's own words) means the PATTERN
(FactRegistration/REGISTRY/validate_registry, FactResult/InsufficientData)
is reused, never the TYPES themselves, per Design Principle VIII.4
(research objects are never structurally interchangeable with production
ones, even when their shapes rhyme) - the same posture Sprint 1 already
took for Feature.definition mirroring FactDefinition.params's shape
without ever importing it.

--- Feature versioning and reproducibility (forward guidance for Sprint 5) ---

A Feature's `version` identifies exactly which computation logic + default
params produced a value. A version never changes in place: a logic or
param change is a brand-new, additively-registered FeatureRegistration
(new feature_id, new version) - never an edit to an existing entry, the
same append-only discipline Rule Engine's own REGISTRY already follows
(Sprint 22B's vwap_relationship was appended, never inserted into an
existing fact) and exactly what the Design Principles' Anti-Patterns table
already forbids under "Silent feature mutations" (VII.4, VIII.5).

A future Experiment (Sprint 5) knows exactly which Feature definition
produced its inputs via feature_id + version + fingerprint - this package
is the first real computation of that fingerprint (Sprint 1 left it
required-but-unpopulated, since nothing existed yet to fingerprint). From
Sprint 5 onward, an Experiment's execution_fingerprint projection (see
replay_bridge.py's own forward-guidance note) must include the
feature_id/version/fingerprint of every Feature its Realization or
criteria reference, alongside code_version/seed - never
semantic_fingerprint's projection, since WHICH VERSION of a feature
computed a number is an execution detail, not a change to which research
question is being asked. Policy only - no Sprint 5 code lives here.
"""

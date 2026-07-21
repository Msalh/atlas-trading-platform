"""
Replay Engine - Phase N2. Deterministically reproduces, bar by bar, the
same derived-state pipeline a live consumer already sees
(RuleEngineOutput, SetupEngineOutput, MarketContext) over an
already-ingested historical MarketState series - see the approved Phase
N2 architecture proposal for the full design (responsibilities, data
flow, dependency diagram, error handling, determinism guarantees, testing
strategy, migration strategy).

Sprint 1 scope only: models.py (ReplayFrame) and segmentation.py
(segment_replay_window). No repository access, no async code, and no
Rule Engine/Setup Engine/Market Context composition yet - see each
module's own docstring.

ReplaySession is explicitly deferred (approved Sprint 1 scope reduction):
a stateful or configuration-wrapper session object should only be
introduced once a real consumer requires pause, resume, step, or
checkpointing behavior. Building it now, with no concrete consumer to
check its shape against, would repeat the "speculative abstraction" this
project has already flagged and avoided at every other layer (e.g. Setup
Engine's own windowing landed only once a real consumer needed it -
Sprint 24C).

Replay Engine may depend on Market Engine models, Rule Engine output
models, Setup Engine output models, Market Context models, and
atlas.profiling.service.segment_by_gap. Nothing under atlas.rule_engine,
atlas.setup_engine, atlas.market_context, or atlas.profiling imports this
package - the dependency arrow points one way only, the same acyclic
shape atlas.market_context's own ADR-0001 already documents for itself
one layer down.
"""

"""
Concrete StrategyPlugin implementations - Phase N3, Sprint 3. Each module
here is one deterministic strategy conforming to
atlas.strategy_engine.ports.StrategyPlugin. No registry exists (or is
planned) - a caller wires whichever plugin instances it wants directly
into atlas.strategy_engine.service.evaluate_strategies(strategies=[...]),
the same explicit-list-no-registry posture Setup Engine's own REGISTRY
docstring contrasts itself against for a genuinely pluggable case.
"""

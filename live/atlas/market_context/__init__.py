"""
Phase N1 - Market Context Foundation. An additive package, deliberately
separate from atlas.market_engine: MarketContext is Atlas's own
INTERPRETATION of the situation a bar occurred in (session phase,
volatility regime) - never a field added to MarketState itself, which stays
exactly what it already was, a record of what a bar objectively did.

This distinction is the whole point of the package boundary, not an
implementation detail: Rule Engine's frozen input signature is
`(MarketState | list[MarketState], FactDefinition)`, and nothing in this
package ever changes that - see models.py's own docstring for the full
reasoning, and docs/market_engine/market-context-architecture.md (once
written) for the approved architecture this package implements.

Sprint 1 scope only: models.py, definitions.py, fingerprint.py. session.py,
regime.py, service.py, and any event/API/UI wiring are deliberately not
part of this package yet - see the approved Phase N1 plan.
"""

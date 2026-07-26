# Product P2A — Proposed Trade and Risk Input Authority

`proposed_trade.v1` binds exactly one deterministic Strategy candidate to one
explicit proposed trade. It is an advisory risk input, never an order,
recommendation, Decision, or execution instruction.

## Authority boundaries

- `EconomicInstrument` is the vendor-neutral product (`MNQ`).
- `MarketDataSeries` is the exact analysis series (`tradingview:MNQ1!`).
- `ListedInstrument` is an independently resolved executable contract.
- A continuous series is never parsed, aliased, or inferred into a listed contract.
- Account and position inputs must be observed, timestamped, reconciled snapshots.
- Instrument specifications and funding rules must come from explicit versioned
  providers. Configuration, webhook claims, inference, mocks, and absence are not
  authoritative production inputs.

## Fail-closed rules

Any missing, stale, future-dated, conflicting, cross-candidate,
cross-instrument, non-authoritative, or unreconciled input refuses alignment.
Refusal produces no approved Risk state. The existing RiskAssessment vocabulary
remains the sole risk result vocabulary: `approved`, `blocked`, `unassessable`,
and `not_applicable`.

Unresolved quantity is explicit. It is refused for fixed sizing and accepted
only when the selected `RiskPolicy` explicitly selects risk-based sizing; it is
never silently inferred by P2A. A target is mandatory only when the selected
`RiskPolicy` requires it.

P2A contains no runtime wiring, API, TraderNow transport, broker integration,
Decision Engine, WAIT/PREPARE/ENTER semantics, AI, persistence, or deployment.

# Product P2B-2A — Runtime Authority Contracts

P2B-2A freezes pure, versioned contracts and read-only ports for future
trade-plan authority resolution. It adds no provider adapter, runtime
composition, API, persistence, cache, database, broker, AI, Risk, Decision,
or execution behavior.

## Contract set

- `trade_plan_authority_resolution.v1`
- `trade_plan_authority_source.v1`
- `trade_plan_effective_interval.v1`
- `listed_contract_authority_request.v1`
- `instrument_specification_authority_request.v1`
- `exchange_session_authority_request.v1`
- `trade_plan_expiry_inputs.v1`
- `trade_plan_policy_authority_request.v1`
- `canonical_market_evidence_authority.v1`

Every result has a deterministic SHA-256 identity, authority kind, explicit
status, provider and source versions, effective interval, observation and
retrieval timestamps, reconciliation state, and a closed reason set.

## Authority outcomes

The only outcomes are `available`, `unavailable`, `stale`, and `conflicting`.
Only `available` carries a value. Every other outcome carries reasons and no
value. Available authority must be reconciled, not future-dated, and effective
at the requested evaluation time.

Missing, stale, overlapping, conflicting, future-dated, unreconciled, or
identity-mismatched authority fails closed. There is no production default,
inference, alias, roll-forward, or fallback.

## Identity boundary

`MNQ` is the economic product. `tradingview:MNQ1!` is the continuous analysis
series. The listed executable contract is an independently resolved exchange
identity. `MNQ1!` is never accepted as the listed executable contract.

## Canonical market evidence

The market-evidence adapter accepts the existing immutable
`MarketInputWindow`. It never fetches, persists, normalizes, canonicalizes, or
regenerates market data. An available result requires exactly 288 observations
and exact agreement between every source-event identity and every canonical
market-state envelope. Its declared timeframe determines an exact expected
cadence; duplicate, non-monotonic, gapped, missing, or mismatched lineage fails
closed. Scheduled maintenance remains part of the preserved raw 288-observation
window, but a gap-spanning window is not eligible as contiguous trade-plan
evidence. P2B does not reinterpret or repair that evidence.

The frozen Context policy is unchanged. `insufficient_history` remains a closed
trade-plan prerequisite failure and must produce no Entry, Stop, Target,
invalidation, confidence, quantity, sizing, or partial geometry.

## Runtime status

No P2B-2A port has a provider implementation. No application, TraderNow,
read-only service, endpoint, dashboard, or deployment imports or invokes
`atlas.trade_plan` or `atlas.trade_plan_authority`.

## Deferred provider ownership

P2B-2B remains blocked until the primary provider, permitted corroborating
source, licensing owner, credential owner, reconciliation approver, freshness
policy, correction policy, and emergency-calendar owner are explicitly
approved for listed-contract, instrument-specification, exchange-calendar, and
trade-plan-policy authority. No provider choice, inferred roll, production
default, or silent fallback exists in P2B-2A.

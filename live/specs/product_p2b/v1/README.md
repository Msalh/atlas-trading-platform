# Product P2B-1 — Deterministic Trade Plan Contracts

P2B-1 freezes a pure-domain planner boundary downstream of Strategy. It can
produce one complete P2A-compatible `ProposedTrade` or one closed refusal. It
does not run in TraderNow and has no API, persistence, provider, calendar,
Risk, Decision, broker, execution, or deployment integration.

## Contract set

The earlier design listed six names while calling them five contracts. P2B-1
resolves that inconsistency as **five versioned contracts**:

1. `trade_plan_input.v1`
2. `trade_plan_policy.v1`
3. `trade_plan_evidence_binding.v1`
4. `trade_plan_result.v1`
5. `trade_plan_refusal.v1`

`trade_plan_refusal.v1` owns the sole closed reason vocabulary. There is no
`trade_plan_reasons.v1` and therefore no duplicate refusal authority.

## Authority and prerequisites

Generation requires one exact Strategy candidate, its exact candidate-bar OHLC
and `SourceEventIdentity`, the containing `MarketInputIdentity`, available
Rules, Setups, Interpretation, and Context, an independently resolved
`ListedInstrument`, an authoritative matching `InstrumentSpecification`, and
an authoritative explicit policy. All evidence must be reconciled, current,
identity-aligned, and timezone-aware.

`MNQ`, `tradingview:MNQ1!`, and an exchange-listed contract are different
identities. `MNQ1!` is never accepted as the listed contract. Golden fixtures
use `TEST-MNQU6`, a test-only identity that is neither a production default nor
contract resolution.

## Geometry

All intermediate arithmetic uses `Decimal`.

- Long: entry = ceil(candidate high + one tick); invalidation = floor(candidate
  low); stop = floor(invalidation - one tick); target = floor(entry + risk
  distance × explicit reward multiple).
- Short is the exact mirror: entry and target round down, invalidation and stop
  round up, and the target rounds conservatively toward entry.
- A long result must satisfy target > entry > invalidation > stop. A short
  result must satisfy target < entry < invalidation < stop.
- Risk distance is at least one tick. Rounding may never collapse or reverse
  geometry.

The reward multiple and `maximum_entry_bars` are mandatory policy inputs with
no defaults. Calendar/session computation is outside P2B-1. The evidence
binding carries an authoritative ordered sequence of eligible future bar-close
timestamps and an authoritative session boundary; expiry is the earlier of
the last permitted bar close and the session boundary.

## Identity and output safety

The plan ID is SHA-256 over deterministic canonical UTF-8 bytes containing the
candidate, source event, market input, candidate OHLC, listed instrument,
instrument specification and authority, policy, geometry, and expiry. JSON
keys are sorted, separators are fixed, timestamps use UTC microseconds, and
Decimals are lossless strings.

A generated result contains exactly one complete `ProposedTrade` and immutable
evidence lineage. Quantity is unresolved. Its safeguards are fixed:

- `purpose = analysis_only`
- `execution_eligible = false`
- `authority = proposed_geometry`
- `requires_risk_assessment = true`
- `requires_separate_decision = true`

It is not ENTER, a recommendation, approval, order, broker instruction, or
execution instruction. Strategy geometry is rejected because it would create
a competing authority.

Any missing, stale, conflicting, insufficient, unresolved, mismatched, or
non-authoritative prerequisite yields `trade_plan_refusal.v1`. Refusal carries
no proposal and no partial Entry, Stop, Target, or invalidation.

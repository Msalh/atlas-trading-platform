# Product P1-R1 — Live Analysis Window Contract

## Status

Implementation contract for Product P1-R1. It changes no API, persistence,
ingestion, Risk, or Decision contract.

## Canonical market evidence versus analysis input

TraderNow acquires and preserves up to 288 closed `MarketState` observations
as its canonical market window. Its `MarketInputIdentity`, source events,
bar count, source-series identity, and transport projection continue to
describe that complete window.

Rule and Setup analysis receive a derived view containing the final maximal
strictly contiguous segment of those same immutable observations:

1. Apply the existing `segment_replay_window()` behavior.
2. Split at every interval that is not exactly the configured timeframe.
3. Select only the final segment, because it contains the canonical latest
   closed bar.
4. Reuse the original `MarketState` objects and complete input identity.

No observation is created, copied into a second authoritative representation,
forward-filled, interpolated, or reordered. Rule Engine window-integrity
validation still executes unchanged after selection.

Scheduled CME maintenance, weekends, holidays, shortened sessions, and an
unexpected missing intraday bar are intentionally treated alike at this
layer: each is a segment boundary. Duplicate and non-monotonic timestamps
remain invalid input rather than segmentation boundaries.

## Insufficient latest segment

The Rule registry determines its minimum history dynamically. If the final
segment contains fewer observations than that requirement:

- Rules are `insufficient_data` with reason `insufficient_history`;
- no Rule output, metadata, or Rule output window is produced;
- Setup, Interpretation, and Strategy remain fail-closed through their
  existing dependency behavior;
- no fact, setup, candidate, Risk, or Decision is fabricated.

Diagnostics contain category names only:

- `market_window_gap`;
- `insufficient_contiguous_history`;
- `rule_engine_failure`.

They contain no payload, timestamp series, exception text, credential, or
infrastructure value.

## Frozen Context boundary

Market Context continues to receive the original canonical 288-observation
window. Product P1-R1 does not alter:

- `REGIME_CLASSIFIER_V1`;
- its 288-observation minimum;
- strict five-minute contiguity;
- invalid-window fallback to `insufficient_history`;
- classifier or calendar versions.

The current MNQ source normally contains a daily maintenance break, while a
strictly contiguous between-break segment contains fewer than 288 five-minute
observations. Context may therefore remain `insufficient_history`.

Resolving that tension requires a separately approved and versioned decision.
Concrete alternatives are:

1. **Observation-count context:** define and recalibrate a new classifier that
   ranks the latest 288 actual observations across disclosed scheduled
   closures while still rejecting unexpected gaps.
2. **Session-segment context:** define and recalibrate a new classifier for
   the maximum continuous CME session segment.
3. **Session-normalized context:** introduce an exchange-calendar-owned
   analysis-window contract that distinguishes scheduled closures from
   missing observations, followed by historical recalibration and replay/live
   equivalence certification.

None is selected or implemented by Product P1-R1.

## Rollback

Rollback is a code revert. No schema, data, ingestion, configuration, or
infrastructure rollback is required. Reverting restores the previous typed
`rule_engine_failure` behavior for gapped 288-observation windows.

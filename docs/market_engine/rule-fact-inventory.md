# Rule Engine — Fact Inventory

**Status: fact catalog, originally approved before Sprint 11 as planning-only. Implementation
status updated through Sprint 13 (2026-07-19) — 6 of the original 13 catalogued facts are now
implemented (`volume_spike`, `displacement`: Sprint 11; `rejection`: Sprint 12; `trend_5m`,
`liquidity_sweep`, `reclaim`: Sprint 13), each marked below with its implementation Sprint and
reconciled to record the implemented baseline rather than pre-implementation placeholder language.
The remaining 7 original facts (the three blocked trend facts, the four reference-level status
facts) are still unimplemented — see "Still unresolved" at the end of this document. Sprint 22B
(2026-07-19) added a 14th fact, `vwap_relationship`, beyond the original 13 — this document's own
scope note below always anticipated that ("facts beyond this set are a future addition to this
same document, not decided here"); see "VWAP facts" below.** Extends
`rule-engine-architecture.md` (which defined what a fact *is* and how Rule Engine output relates
to the LLM) into a concrete, per-fact catalog. Sprints 11–13 implemented against this document; it
does not redesign the boundary decisions already made in `architecture-principles.md` or
`rule-engine-architecture.md`.

## Scope of this inventory

This inventory deliberately covers exactly the fields already reserved in `MarketState`'s schema
since Sprint 1/2 but left as `null`/`false` placeholders by Sprint 5's Pine script: the 4 trend
fields, the 5 boolean pattern flags, and the 4 reference-level status fields. This is not an
arbitrary starting set — it is the specific, already-disclosed gap `rule-engine-architecture.md`
identified. Facts beyond this set are a future addition to this same document, not decided here.

**Important clarification, stated once rather than repeated 13 times below**: every fact here
reuses the *name and conceptual shape* already reserved in `MarketState` (so the mapping to
existing knowledge is obvious), but the Rule Engine does **not** write into `MarketState` to
populate them. `market_state_events` rows are immutable once stored (Immutability Rules); the
Rule Engine instead produces its own, separately-owned output object carrying the same facts,
computed fresh from stored data — never a mutation of a stored row.

**On "Confidence or score"**: most facts below are deterministic classifications (a boolean or an
enum), not scored predictions — for those, a confidence score is explicitly not applicable, by
design. Introducing one would blur the deterministic/probabilistic boundary
`rule-engine-architecture.md` exists to protect. Where a fact's own field says "N/A," that is a
deliberate answer, not an omission. **Correction**: N/A means no probabilistic confidence is
invented — it does not mean the numerical evidence behind the classification is discarded. Where
a fact is threshold-derived (a ratio or measurement compared against a cutoff), the fact's output
should preserve that evidence alongside the boolean/enum result — e.g. `volume_spike` should carry
the `volume_ratio` value and the threshold it was compared against, not just `true`/`false`;
`displacement` should carry the range/ATR ratio and its threshold. This makes each fact
independently auditable (why did this fire?) without introducing a fabricated probability. Noted
per-fact below where it applies.

**Readiness, an addition beyond your requested fields**: for each fact I've noted whether it's
computable today from the one confirmed ingestion stream (`pine/MNQU6_market_state_v1.pine`,
5-minute bars) or blocked on data that doesn't exist yet. This surfaced a real finding worth
having before Sprint 11 is scoped: several trend facts need timeframes this system has never
ingested. Flagging this now, not silently discovering it mid-Sprint.

---

## Trend facts

### trend_5m
**Status: implemented, Sprint 13.** `atlas.rule_engine.facts.evaluate_trend_5m`. Window=20,
OLS slope over closes, projected across the window, normalized by the current bar's `atr`,
classified up/down/flat against ±1.0 — all formally specified at Sprint 13's approval, not
Claude's own guess (contrast `reclaim`'s window, defined further below, which was Claude's own
choice, later formally ratified).
- **Category**: Trend
- **Inputs**: close prices over a 20-bar lookback window of 5-minute bars
- **Required history window**: **20 bars (implemented baseline)** — see
  `DEFAULT_TREND_5M_DEFINITION` in `atlas/rule_engine/definitions.py`.
- **Formula/computation method**: **implemented baseline** — an OLS (ordinary least squares)
  slope fitted over the window's closes, projected across the window
  (`slope * (window_size - 1)`), normalized by the current bar's `atr`
  (`normalized_move = projected_move / atr`), classified `"up"` if `normalized_move > 1.0`,
  `"down"` if `< -1.0`, `"flat"` otherwise.
- **Output type**: enum (`"up"` / `"down"` / `"flat"`), carrying `slope`, `projected_move`, `atr`,
  `normalized_move`, and both thresholds as evidence
- **Confidence or score**: N/A (deterministic) — evidence preserved instead, per the general
  principle above
- **Dependencies on other facts**: none
- **Readiness**: **Ready.** The only fact in the trend group computable from the one ingestion
  stream that exists today.

### trend_1m
- **Category**: Trend
- **Inputs**: close prices over a lookback window of 1-minute bars
- **Required history window**: N most-recent 1m bars
- **Formula/computation method**: same method family as `trend_5m`, applied at 1m granularity
- **Output type**: enum (`"up"` / `"down"` / `"flat"`)
- **Confidence or score**: N/A
- **Dependencies on other facts**: none
- **Readiness**: **Blocked — hard blocker, no aggregation path exists.** No 1-minute
  `market_state` ingestion stream exists, and none can be synthesized: aggregation only works from
  higher resolution to lower resolution (many 5m bars can be combined into one 15m or 1h bar), not
  the reverse — a 5m bar's internal 1-minute price path is not recoverable from the 5m OHLCV
  values alone. `trend_1m` requires a real, dedicated 1-minute ingestion source (a second
  TradingView indicator publishing at 1m); there is no other path to unblocking it.

### trend_15m
- **Category**: Trend
- **Inputs**: close prices over a lookback window of 15-minute bars
- **Required history window**: N most-recent 15m bars
- **Formula/computation method**: same method family as `trend_5m`, applied at 15m granularity
- **Output type**: enum (`"up"` / `"down"` / `"flat"`)
- **Confidence or score**: N/A
- **Dependencies on other facts**: none
- **Readiness**: **Blocked today — soft blocker, a real aggregation path exists.** No 15m stream
  exists yet, but three consecutive 5m bars aggregate cleanly into one 15m bar (coarsening
  resolution is valid, unlike `trend_1m`'s case). Unblocked by a future 5m→15m aggregation
  capability, not by new ingestion.

### trend_1h
- **Category**: Trend
- **Inputs**: close prices over a lookback window of 1-hour bars
- **Required history window**: N most-recent 1h bars
- **Formula/computation method**: same method family as `trend_5m`, applied at 1h granularity
- **Output type**: enum (`"up"` / `"down"` / `"flat"`)
- **Confidence or score**: N/A
- **Dependencies on other facts**: none
- **Readiness**: **Blocked today — soft blocker, a real aggregation path exists.** No 1h stream
  exists yet, but twelve consecutive 5m bars can aggregate into one 1h bar, the same direction of
  aggregation as `trend_15m`. Requires explicit session-boundary handling as part of that future
  aggregation work (does an hour spanning the daily maintenance window aggregate correctly, or
  does it need to be excluded/split?) — a real design question, not analyzed here, but the
  aggregation direction itself is sound, unlike `trend_1m`.

## Liquidity interaction facts

### liquidity_sweep
**Status: implemented, Sprint 13.** `atlas.rule_engine.facts.evaluate_liquidity_sweep`.
- **Category**: Liquidity interaction
- **Inputs**: recent bar highs/lows; one or more reference levels (`previous_day_high`,
  `previous_day_low`, `overnight_high`, `overnight_low` — all already sent raw by TradingView,
  not placeholders)
- **Required history window**: **3 bars (approved baseline)** — see `DEFAULT_LIQUIDITY_SWEEP_DEFINITION`
  in `atlas/rule_engine/definitions.py`. Explicitly specified in the Sprint 13 approval ("three-bar
  resolution window"), not an implementation guess.
- **Formula/computation method**: for a high-side level, some bar's high in the window reaches or
  breaches it AND the current bar's close is back below it; for a low-side level, the symmetric
  low/above-close condition. Every qualifying level's excursion (the most extreme breaching
  high/low in the window, and which bar produced it) is preserved.
- **Output type**: boolean, carrying a `qualifying_levels` list (reference level, side, level,
  excursion, excursion bar, current close) as evidence — not a bare `true`/`false`
- **Confidence or score**: N/A (deterministic) — evidence preserved instead, per the general
  principle above
- **Dependencies on other facts**: **none — resolved, Sprint 13.** `reclaim` does NOT depend on
  `liquidity_sweep`; the two are defined and computed independently (see `reclaim`'s entry below).
  The two can and do disagree on the same window: a bar can wick through a level (`liquidity_sweep`
  fires) without its close ever crossing it (`reclaim` does not fire), and this is tested explicitly
  (`test_does_not_depend_on_liquidity_sweep`).
- **Readiness**: **Ready** — the 5m stream plus the already-raw reference levels are sufficient.

### reclaim
**Status: implemented, Sprint 13.** `atlas.rule_engine.facts.evaluate_reclaim`.
- **Category**: Liquidity interaction
- **Inputs**: recent bar closes; the same reference levels as `liquidity_sweep`
- **Required history window**: **3 bars — formally approved as the baseline (2026-07-19),
  superseding this document's earlier "TBD".** See `DEFAULT_RECLAIM_DEFINITION` in
  `atlas/rule_engine/definitions.py`. Provenance, for anyone revisiting this later: unlike
  `liquidity_sweep`'s window (explicitly specified at approval time), `reclaim`'s window size was
  not given in the Sprint 13 spec — Claude chose 3 to match `liquidity_sweep`'s window, for
  consistency between the two remaining liquidity-interaction facts, and flagged it as an
  unvalidated heuristic (Sprint 13's Engineering Heuristics, TD-16). The user has now formally
  ratified that choice as the approved baseline: **future Sprints should treat `reclaim`'s 3-bar
  window as an intentional design decision, not an unresolved implementation detail** — changing
  it should go through the same disclosed-decision process as any other rule definition change,
  not be silently adjusted as if it were still a placeholder.
- **Formula/computation method**: a prior (earlier-in-window) close beyond a reference level,
  followed by the current bar's close back across the level to the origin side. "Origin side" is
  Claude's own disclosed interpretation, not explicitly specified: for a low-side level (support)
  the origin side is above; for a high-side level (resistance) the origin side is below.
- **Output type**: boolean, carrying a `qualifying_levels` list (reference level, side, level,
  break close + bar, current close) as evidence
- **Confidence or score**: N/A (deterministic) — evidence preserved instead
- **Dependencies on other facts**: **none — resolved, Sprint 13.** Deliberately does NOT depend on
  `liquidity_sweep`, per explicit Sprint 13 direction; see `liquidity_sweep`'s entry above for the
  test proving the two facts are independent.
- **Readiness**: **Ready**, same data sources as `liquidity_sweep`.

### rejection
**Status: implemented, Sprint 12.** `atlas.rule_engine.facts.evaluate_rejection`. Single
current bar, wick/effective-body ratio threshold=2.0, all four reference levels checked
independently.
- **Category**: Liquidity interaction
- **Inputs**: the current bar's open/high/low/close (wick structure); the four reference levels
  (`previous_day_high`, `previous_day_low`, `overnight_high`, `overnight_low`)
- **Required history window**: **current bar only (implemented baseline)** — no prior bars
  needed.
- **Formula/computation method**: **implemented baseline** — checked independently against all
  four reference levels. High-side: the bar's high reaches or breaches the level AND the close
  finishes below it. Low-side: the symmetric low/above-close condition. For each qualifying
  level, `wick / effective_body > 2.0`, where `effective_body = max(abs(close - open),
  tick_size)` — the effective body is floored by the instrument's tick size (sourced from
  `atlas.market_engine.constants.TICK_SIZE`) so a near-zero-body bar never produces a
  division-by-a-tiny-number ratio blowup. All qualifying levels are preserved, not just one.
- **Output type**: boolean, carrying a `qualifying_levels` list (reference level, side, level,
  wick length, raw body length, effective body, wick/body ratio, close distance from level) as
  evidence
- **Confidence or score**: N/A (deterministic) — evidence preserved instead
- **Dependencies on other facts**: none
- **Readiness**: **Ready.**

### displacement
**Status: implemented, Sprint 11, retrofitted onto FactDefinition in Sprint 12.**
`atlas.rule_engine.facts.evaluate_displacement`. Threshold=1.5, range (not body) definition.
- **Category**: Liquidity interaction / volatility
- **Inputs**: current bar's range (high − low); `atr` (already sent raw by TradingView, not a
  placeholder)
- **Required history window**: current bar only, plus whatever window `atr` itself was computed
  over upstream (already done by TradingView, not the Rule Engine's concern)
- **Formula/computation method**: **implemented baseline** — `displacement = (high - low) / atr
  > 1.5`. 1.5 is the implemented threshold; it remains an unvalidated heuristic (no real
  production traffic has exercised this system yet), not a measured value — see Sprint 11/13's
  Engineering Heuristics review sections.
- **Output type**: boolean, carrying the underlying range/ATR ratio and the threshold it was
  compared against as evidence — not a bare `true`/`false`
- **Confidence or score**: N/A (deterministic) — evidence preserved instead: the computed
  range/ATR ratio and the threshold used, so the result is auditable without inventing a
  probability
- **Dependencies on other facts**: none
- **Readiness**: **Ready** — needs no history window beyond the current bar plus an already-raw
  field. The second-simplest fact in this inventory.

## Volume facts

### volume_spike
**Status: implemented, Sprint 11, retrofitted onto FactDefinition in Sprint 12.**
`atlas.rule_engine.facts.evaluate_volume_spike`. Threshold=1.5.
- **Category**: Volume
- **Inputs**: `volume_ratio` (already sent raw by TradingView, not a placeholder — Sprint 5's
  docstring names only 5 boolean flags and 4 status fields as deferred; `volume_ratio` was not
  among them)
- **Required history window**: **none** — a pure threshold on a value already present in the
  current `MarketState`
- **Formula/computation method**: **implemented baseline** — `volume_spike = volume_ratio >
  1.5`. 1.5 is the implemented threshold; it remains an unvalidated heuristic (no real production
  traffic has exercised this system yet), not a measured value — see Sprint 11/13's Engineering
  Heuristics review sections.
- **Output type**: boolean, carrying the `volume_ratio` value and the threshold it was compared
  against as evidence — not a bare `true`/`false`
- **Confidence or score**: N/A (deterministic) — evidence preserved instead: the `volume_ratio`
  value and the threshold used, so the result is auditable without inventing a probability
- **Dependencies on other facts**: none
- **Readiness**: **Ready — and the simplest fact in this entire inventory.** No window, no
  cross-bar logic, a single-field threshold on data that's already stored. A strong candidate for
  the very first fact Sprint 11 implements, precisely because it's the smallest possible proof of
  the whole Rule Engine pattern.

## VWAP facts

Not part of the original 13-field scope (see this document's status line) — added Sprint 22B, the
first fact beyond that original set, following a dedicated design Sprint (22A) and one further
design-review round over the output contract.

### vwap_relationship
**Status: implemented, Sprint 22B.** `atlas.rule_engine.facts.evaluate_vwap_relationship`.
Threshold=1.0.
- **Category**: VWAP
- **Inputs**: `distance_from_vwap_points` and `atr` (both already sent raw by TradingView, not
  placeholders — confirmed by reading `pine/MNQU6_market_state_v1.pine` directly:
  `distanceFromVwapPoints = close - vwapValue`, so the field is **signed** — positive when price is
  above VWAP, negative when below — and denominated in points, not ticks)
- **Required history window**: **none** — current bar only, the same shape as `volume_spike`/
  `displacement`
- **Formula/computation method**: **implemented baseline** — `normalized_distance =
  distance_from_vwap_points / atr` (ATR-normalized for regime stability, the same normalization
  `displacement` and `trend_5m` already use — raw points or ticks were considered and rejected in
  Sprint 22A specifically because neither is regime-stable). Classified `"extended_above"` if
  `normalized_distance > 1.0`, `"extended_below"` if `< -1.0`, `"within_band"` otherwise — strictly
  greater/less than, matching every other fact's boundary convention. 1.0 is a provisional,
  explicitly unvalidated heuristic (no real production traffic has ever exercised this system),
  borrowed from `trend_5m`'s own threshold shape as the closest existing precedent.
- **Output type**: three-way enum (`"extended_above"` / `"extended_below"` / `"within_band"`),
  carrying `distance_from_vwap_points`, `atr`, `normalized_distance`, and `threshold` as evidence.
  Deliberately not `"above"`/`"below"`/`"near"` (an earlier design considered and rejected in
  Sprint 22A's review) — that vocabulary mixed direction language with magnitude language inside
  one enum; all three of the chosen values instead describe the same question (position relative
  to the threshold band).
- **Confidence or score**: N/A (deterministic) — evidence preserved instead, per the general
  principle above
- **Dependencies on other facts**: none
- **Readiness**: **Ready.** Both required inputs are already-raw wire fields; no new ingestion, no
  aggregation work, no session-boundary logic needed.

## Reference-level status facts

### overnight_high_status / overnight_low_status / previous_day_high_status / previous_day_low_status
Grouped together — all four share an identical shape, differing only in which reference level and
which side of price they track.

- **Category**: Reference-level status
- **Inputs**: recent bar highs/lows/closes; the relevant reference level (`overnight_high`,
  `overnight_low`, `previous_day_high`, or `previous_day_low` — all already raw)
- **Required history window**: since the level was established (session start for overnight
  levels, previous session close for previous-day levels) through the current bar — a
  session-aware window, not a fixed bar count; exact boundary logic deferred to implementation
- **Formula/computation method**: a status enum tracking whether price has interacted with the
  level yet this session/day (observed values in existing test fixtures: `"untested"`,
  `"reclaimed"`, `"swept"` — the authoritative value set and transition logic between them is an
  implementation decision, not fixed here)
- **Output type**: enum (string status)
- **Confidence or score**: N/A
- **Dependencies on other facts**: likely relates to `liquidity_sweep`/`reclaim` above (a "swept"
  status plausibly means a sweep fact fired against this specific level) — whether these four
  facts are derived FROM `liquidity_sweep`/`reclaim`, or computed independently with their own
  logic, is an open implementation question, not decided here
- **Readiness**: **Ready**, data-wise — but the session-boundary window (needing to know "since
  when" for each level) is more design work than the other ready facts above, since it requires
  reasoning about session start/close, not just a fixed bar count.

---

## Summary — data readiness across all 13 facts

13 facts total. **10 are data-ready today**; 3 are blocked.

| Fact | Readiness |
|---|---|
| `volume_spike` | Ready — no window needed |
| `displacement` | Ready — current bar only |
| `liquidity_sweep` | Ready |
| `reclaim` | Ready — independent of `liquidity_sweep` (resolved, Sprint 13) |
| `rejection` | Ready |
| `trend_5m` | Ready |
| `overnight_high_status` / `overnight_low_status` / `previous_day_high_status` / `previous_day_low_status` | Ready, more design work (session-boundary windows) — 4 facts |
| `trend_1m` | **Blocked — hard blocker.** No aggregation path; requires a real 1m ingestion source |
| `trend_15m` | **Blocked today — soft blocker.** A real path exists: future 5m→15m aggregation |
| `trend_1h` | **Blocked today — soft blocker.** A real path exists: future 5m→15m→1h aggregation, plus explicit session-boundary handling |

(6 individually-listed ready facts + the 4 grouped status facts = 10 ready. 3 blocked. 10 + 3 =
13.)

**Data readiness is not the same as Sprint 11 scope.** Being data-ready only means a fact *could*
be computed with data that exists — it says nothing about whether its exact definition (window
size, thresholds, session-boundary logic, and, at the time, the now-resolved reclaim/sweep
dependency question) is settled enough to implement yet. Sprint 11's actual scope was
deliberately much narrower than "everything data-ready" — see below (historical).

## Historical Sprint 11 scope — completed

Retained for traceability. This section describes what was decided *before* Sprint 11 began,
including open questions (like the reclaim/sweep dependency) that Sprint 13 has since resolved —
read it as the historical record of that scoping decision, not as current status. See each fact's
own entry above, and the "Resolved through Sprint 13" section below, for current status.

At the time, Sprint 11 did **not** implement all 10 data-ready facts. Trend, liquidity
interaction, and session-status facts were deferred to later slices, after their exact
definitions (window sizes, thresholds, the reclaim/sweep dependency question, session-boundary
logic) were fixed — none of that design work had been done yet, and building against an
unsettled definition would have meant rebuilding it once the definition firmed up.

Sprint 11 built only:

- **Rule Engine package/foundation** — the new domain package itself (name/location decided at
  implementation time, per `rule-engine-architecture.md`'s deferral).
- **Versioned output type** — the Rule Engine's own, separately-owned output object (never a
  mutation of `MarketState`), carrying a version marker per `rule-engine-architecture.md`'s
  Outputs section.
- **Explicit insufficient-data representation** — the EmptyResult/InvalidRange-equivalent
  distinction flagged (not resolved) in both prior planning documents, resolved now: a fact
  computed with genuinely insufficient history must be distinguishable from a fact that computed
  cleanly and found nothing notable.
- **`volume_spike`** — the simplest fact in the inventory, no window, evidence-preserving.
- **`displacement`** — the second-simplest, current-bar-only, evidence-preserving.
- **Deterministic and replay reproducibility tests** — proving the same input (live or replayed)
  always produces the same output, the property the whole Rule Engine design depends on.

This gave Sprint 11 a working, tested, versioned Rule Engine with exactly two real facts —
enough to prove the whole pattern end to end (foundation, output type, insufficient-data handling,
evidence preservation, reproducibility) without committing to any of the harder definitions that
were still unsettled at the time (trend windows, liquidity thresholds, the reclaim/sweep
dependency question). Those followed in later, narrower slices once each one's definition was
fixed: `rejection` in Sprint 12; `trend_5m`, `liquidity_sweep`, and `reclaim` in Sprint 13. The
aggregation work `trend_15m`/`trend_1h` will eventually need, and the four status facts'
session-boundary logic, remain unbuilt — see "Still unresolved" below.

## Resolved through Sprint 13

What was open when this document was first written and has since been settled by implementation:

- The `atlas/rule_engine` package itself (foundation, Sprint 11).
- `RuleEngineOutput` (the versioned output envelope, Sprint 11).
- `FactResult` / `InsufficientData` (the explicit insufficient-data representation, Sprint 11).
- Every implemented fact's window size and threshold: `volume_spike` (no window, threshold 1.5),
  `displacement` (no window, threshold 1.5), `rejection` (no window, wick/effective-body ratio
  threshold 2.0), `trend_5m` (20-bar window, OLS slope, ±1.0 normalized-move thresholds),
  `liquidity_sweep` (3-bar window), `reclaim` (3-bar window, formally ratified as the approved
  baseline — see `reclaim`'s own entry above).
- The `reclaim`/`liquidity_sweep` independence question — resolved as independent, Sprint 13,
  with a dedicated test proving it.

## Still unresolved

What remains genuinely open, for a future slice to resolve as an implementation question, not for
this document to guess at:

- The four reference-level status facts' (`overnight_high_status`, `overnight_low_status`,
  `previous_day_high_status`, `previous_day_low_status`) transition definitions — the
  authoritative value set (`"untested"`/`"reclaimed"`/`"swept"` are observed test-fixture values,
  not a ratified set) and the logic governing transitions between them.
- Session-boundary logic for those same four status facts (needing to know "since when" a level
  has been in play — session start for overnight levels, previous session close for previous-day
  levels).
- 5m→15m and 5m→1h aggregation implementation — `trend_15m`/`trend_1h`'s feasibility is resolved
  (a real aggregation path exists), but the aggregation capability itself is not built.
- Real 1m ingestion — `trend_1m`'s only path forward (a second TradingView indicator publishing
  at 1m); no aggregation path exists for it, unlike the two facts above.
- Empirical validation and retuning of every implemented heuristic (the 1.5/2.0/±1.0 thresholds,
  the 3-bar/20-bar windows) — all remain unvalidated against real data, since no production
  traffic has ever exercised this system.

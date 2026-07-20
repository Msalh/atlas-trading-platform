# RE-1 Research Notes — Five-File Baseline

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Row count**: 97,858
- **Code version**: a907325fbb357097fb0e8e064d46772e2b719964
- **Generated**: 2026-07-20 (see the five RE1_*.md reports for the underlying computed statistics — this document introduces no new calculations of its own, only a reading of results already in those reports)

No trading conclusions. No alpha claims. No expectancy. No forward returns. This is a summary reading of RE-1's own descriptive output, nothing more.

## 1. Structural relationships (guaranteed by fact definitions, not empirical findings)

Two of the ten boolean-fact pairs in `RE1_RuleRelationships.md` are not independent discoveries — they are logical consequences of how the facts are defined in `atlas/rule_engine/facts.py`, proven directly from the fact definitions (Sprint 24A Rule Fact Independence Audit, `docs/market_engine/rule-fact-inventory.md`, "Fact hierarchy within this family"):

- **`rejection=True` implies `liquidity_sweep=True`** on the same reference level, whenever both are computable — a rejection's wick-breach-then-close-back condition is a strict subset of a sweep's own breach condition.
- **`reclaim=True` implies `liquidity_sweep=True`** on the same reference level (configuration-contingent: holds when both facts share the same window).

The empirical data confirms both hold almost exactly as proven: P(rejection ∩ liquidity_sweep) = 2.8% ≈ P(rejection) = 2.8%, and P(reclaim ∩ liquidity_sweep) = 3.1% ≈ P(reclaim) = 3.1% — i.e. essentially every computable `rejection` or `reclaim` bar also has `liquidity_sweep=True`, exactly as the hierarchy proof predicts. Their high lift/correlation numbers (4.498 / 0.317 and 4.498 / 0.332) reflect this logical containment, not a market discovery, and should never be read as one.

## 2. Strongest genuinely empirical (non-structural) relationship

**`volume_spike` × `displacement`** — lift 5.067, Pearson correlation 0.584, P(displacement | volume_spike) − P(displacement) = +0.604. This is by far the strongest non-structural association in the dataset (next highest correlation among non-structural pairs is 0.142). `volume_spike` (a `volume_ratio` threshold) and `displacement` (a body/ATR-based range threshold) are computed from unrelated MarketState fields with no shared precondition — this co-occurrence is a real, descriptive property of this instrument's actual bar-to-bar behavior over the covered period, not a definitional artifact.

## 3. Weak / approximately-independent relationships

Ordered by Pearson correlation, excluding the two structural pairs above:

| pair | lift | correlation |
|---|---|---|
| volume_spike × displacement | 5.067 | 0.584 |
| volume_spike × liquidity_sweep | 1.636 | 0.142 |
| displacement × liquidity_sweep | 1.591 | 0.108 |
| rejection × reclaim | 3.920 | 0.088 |
| displacement × reclaim | 2.147 | 0.069 |
| volume_spike × rejection | 1.906 | 0.065 |
| volume_spike × reclaim | 1.761 | 0.057 |
| displacement × rejection | 1.427 | 0.025 |

`displacement × rejection` is the closest to independence in the dataset (correlation 0.025). `rejection × reclaim`'s elevated lift (3.920) despite a modest correlation (0.088) is consistent with a rare-event lift-inflation artifact — both facts individually occur on well under 3.5% of bars, and lift is known to amplify for two rare events even under near-independence; this should not be read as a strong relationship without also weighing the correlation figure.

## 4. Persistence — the most information-dense finding in this baseline

`trend_5m` is strongly self-persistent: `down`→`down` 93.3%, `up`→`up` 93.6% per-bar transition probability, with mean run lengths of 14.0 and 14.8 bars respectively (`flat` is the least persistent trend state: 82.8% self-transition, mean run 5.7 bars). `liquidity_sweep=True` is also self-reinforcing once triggered: 78.1% chance the next bar is still `True`, mean true-run length 4.48 bars — sweeps cluster rather than firing as isolated single-bar events. By contrast, `rejection` and `reclaim` are both rare AND short-lived (mean true-run lengths 1.10 and 1.67 bars) — they behave as near-instantaneous single-bar events rather than sustained conditions, structurally different in character from `liquidity_sweep` and `trend_5m` despite the hierarchy relationship in §1.

## 5. Time / session concentration (descriptive only)

- **08:00 CT** is the single most active hour in the dataset by a wide margin: `volume_spike` 61.5%, `displacement` 40.2% — both far above every other hour (next-highest `volume_spike` hour is 07:00 at 30.2%). This aligns with the RTH session's opening window.
- **15:00 CT** shows the highest `liquidity_sweep` rate of any hour (61.0%, vs. a dataset-wide average of ~22%) alongside the highest `rejection` rate (9.2%) — consistent with elevated wick activity around the RTH session's close.
- **17:00 CT**, the overnight session's reopen hour immediately after the daily maintenance halt, also shows an elevated `liquidity_sweep` rate (45.2%).
- **10:00–14:00 CT** is comparatively quiet across every fact (`volume_spike` as low as 1.5% at 10:00), consistent with a mid-session lull between the open and close.
- **Session-level**: RTH bars show higher `volume_spike` (16.4% vs 14.2%), `displacement` (12.9% vs 9.7%), and especially `reclaim` (6.7% vs 1.6%) than OVERNIGHT bars, while OVERNIGHT shows a higher `liquidity_sweep` rate (24.9% vs 15.4%) — plausibly reflective of thinner overnight liquidity producing more wick-based sweeps without full reclaim follow-through.
- **Sunday** (the shortened weekly reopen session, 6,059 bars — the smallest weekday bucket) shows the lowest activity of any weekday across every fact (`displacement` 6.2%, `volume_spike` 8.0%), consistent with thin reopen liquidity.

These are purely descriptive concentrations in the observed data — not a claim that any hour, session, or weekday is more tradeable.

## 6. Data-quality caveats carried into this baseline

Full detail: [`docs/market_engine/re1-5file-phase3-certification-report.md`](../docs/market_engine/re1-5file-phase3-certification-report.md).

- **`trend_1m` is unreliable before 2025-07-20** (100% null from the dataset's start through that date, a hard cutoff 365 days before this run's date — evidence points to a TradingView 1-minute-history lookback limit, not a pipeline defect) and has a smaller, separate, ordinary-warmup-shaped null cluster at File 5's start (2026-04-05 to 04-08). **This does not affect any RE-1 report** — `trend_1m` is a raw wire field, never consumed by the 7 registered Rule Engine facts RE-1 actually profiles. It is disclosed here only because a future consumer of the raw field must know about it.
- **ATR has 39 nulls**, clustered in three 13-bar groups precisely at file-start boundaries not masked by dedup overlap — confirmed legitimate per-export `ta.atr(14)` warmup, not a defect.
- The formal certifier verdict for the merged dataset is **REJECTED** under this project's strict-AND certification rule (the `trend_1m` FAIL above is sufficient to reject on its own), while the certification report's own interpretive section concludes the dataset **is** fit for descriptive Setup Profiling specifically because that one FAIL sits entirely outside RE-1's scope. Any future work that reads `trend_1m` directly must re-examine this distinction rather than relying on RE-1's "fit for purpose" reading.
- Instrument identity (`MNQ1!`) is CLI-asserted, not extracted from the CSVs (no symbol column exists in TradingView's chart export); there remains no per-instrument tick-size/roll registry in this codebase (standing architectural debt, unchanged by this sprint).
- No contract-roll discontinuity was found at any of the four file-transition boundaries, but this project has no independent way to detect or date individual rolls within a continuous-contract series — a disclosed limitation, not a new one.

## 7. Implications for RE-2 design

- Any RE-2 hypothesis or analysis touching `rejection` or `reclaim` alongside `liquidity_sweep` must account for §1's structural containment explicitly — a naive "these two facts often occur together" framing would be reporting a tautology, not a finding.
- `volume_spike × displacement` (§2) is the one non-structural relationship in this baseline strong enough to be worth a dedicated RE-2 hypothesis, if RE-2's scope extends to joint-fact conditioning.
- `trend_5m`'s strong persistence (§4) means any RE-2 design that treats consecutive bars as independent observations (e.g. a naive win-rate calculation across the whole series) will be counting highly autocorrelated bars as independent evidence — RE-2 will need a run-aware or session-aware sampling design, not a bar-by-bar one, to avoid overweighting single long trend runs.
- The 08:00 / 15:00 / 17:00 CT concentrations (§5) suggest RE-2, if it studies time-of-day effects, should treat hour-of-day as a first-class conditioning variable rather than pooling all hours together — this baseline's own conditional probabilities (`RE1_ConditionalProbability.md`) already show meaningfully different fact rates by hour.
- `trend_1m` should be excluded from any RE-2 analysis of the pre-2025-07-20 portion of this dataset entirely, per §6 — RE-2 must not attempt to "fill in" or infer values across that boundary.

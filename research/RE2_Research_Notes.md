# RE-2 Research Notes — Setup Profile Baseline

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Row count**: 97,858
- **Code version**: 806e4f1ae2386a68207192089ab303d77c05fa66
- **Generated**: 2026-07-20 (see the six RE2_*.md reports for the underlying computed statistics — this document introduces no new calculations, only a reading of results already in those reports)

Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate content anywhere below.

## 1. Setup frequency and persistence

| setup | active bars | active rate | episodes | median duration | p95 duration | max duration |
|---|---|---|---|---|---|---|
| displacement_with_volume_confirmation | 7,786 | 8.0% | 5,270 | 1 bar | 4 bars | 10 bars |
| liquidity_sweep_with_volume_confirmation | 5,263 | 5.4% | 2,970 | 1 bar | 4 bars | 11 bars |
| sustained_displacement_streak | 3,021 | 3.1% | 1,708 | 1 bar | 5 bars | 9 bars |
| vwap_extension_with_volume_confirmation | 11,467 | 11.7% | 6,331 | 1 bar | 5 bars | 14 bars |

Every setup is dominated by single-bar episodes (roughly 55–75% of all episodes last exactly one bar; see `RE2_Setup_Profile.md`'s `single_bar_episode_count`/`multi_bar_episode_count`) — these are brief, punctual conditions, not sustained regimes, in sharp contrast to RE-1's finding that the underlying `trend_5m` fact is highly persistent (93%+ same-value continuation). Composing a raw fact with `volume_spike` (a comparatively rare, short-lived condition) or requiring a 2+ bar streak visibly shortens the resulting episode's typical lifetime relative to the raw fact's own run-length.

Censoring is rare and does not materially affect any of the above: left-censored episodes range from 0 (liquidity_sweep, sustained_displacement_streak) to 33 (displacement, 0.6% of its episodes); right-censored episodes are 2–4 per setup out of thousands. All-episodes and fully-observed-only duration statistics are identical to two decimal places for every setup (see `RE2_Setup_Profile.md`) — censoring has no detectable effect on the duration distributions at this dataset's scale.

## 2. Time concentration

**All four setups show their strongest concentration at 08:00 CT**, each by a wide margin over every other hour:

| setup | dataset-wide active-bar rate | 08:00 CT active-bar rate | 08:00 CT activation rate |
|---|---|---|---|
| displacement_with_volume_confirmation | 8.0% | 39.7% | 14.7% |
| liquidity_sweep_with_volume_confirmation | 5.4% | 18.0% | 7.5% |
| sustained_displacement_streak | 3.1% | 25.2% | 9.1% |
| vwap_extension_with_volume_confirmation | 11.7% | 47.2% | 15.8% |

For the three `volume_spike`-driven setups (displacement, liquidity_sweep, vwap_extension), this sits directly adjacent to RE-1's own finding that 08:00 CT is the peak hour for the underlying `volume_spike`/`displacement` facts (RE1_Research_Notes.md §5) — expected, since `volume_spike` is a required input to all three.

`sustained_displacement_streak` requires no `volume_spike` at all, yet independently shows the same 08:00 CT concentration (25.2% active-bar rate, roughly 8x its own dataset-wide rate) — a genuinely separate observation, not inherited from a shared input fact. Both findings describe a real, descriptive time concentration in this dataset; neither is evidence of what causes bars near 08:00 CT to behave this way, and no causal mechanism is asserted here.

Session-level: every setup's activation rate is broadly similar between OVERNIGHT and RTH (within a few percentage points), but `displacement_with_volume_confirmation`'s active-bar rate is meaningfully higher in RTH (10.3%) than OVERNIGHT (7.0%) — RTH's greater average volume plausibly produces more sustained displacement runs once triggered, consistent with RE-1's own RTH-vs-OVERNIGHT displacement finding.

Friday shows the highest episodes-per-trading-day for displacement (11.49, versus 6.97–7.86 on other weekdays) — Friday's shorter average trading-day coverage (71 eligible days vs 142–146 for other weekdays, since MNQ1! sessions frequently end early or the week's data coverage is thinner near Fridays) concentrates a comparable activation count into fewer eligible days, inflating the per-day rate; the activation-rate-per-bar figure (6.1%) is much closer to the other weekdays' range and is the more reliable comparison.

## 3. Clustering

Every setup shows a heavy-tailed inter-episode gap distribution: median gaps range from 35 minutes (vwap_extension) to 140 minutes (sustained_displacement_streak), while p95 gaps reach 225–475 minutes. "Repeat activation within 15 minutes" is common for the three volume_spike-driven setups (23–28% of within-segment gaps) but rare for `sustained_displacement_streak` (9.2% of its gaps) — streaks take longer to re-form after ending, consistent with §1's earlier point that this setup captures a comparatively slower-forming, non-repeating condition.

Burst sizes (maximal runs of episodes each within a threshold of the last) grow substantially as the threshold widens — e.g. `vwap_extension_with_volume_confirmation`'s longest observed burst grows from 8 episodes (≤15min) to 12 (≤30min) to 15 (≤60min) — showing clustering is a real, threshold-sensitive property of this data, not an artifact of any one arbitrary cutoff (per amendment 9, no single threshold is treated as canonical here).

`censored_by_gap` counts (357–359 per setup) closely track the dataset's 359 total market-data segments (RE-1 Phase 3 certification report §5: 358 gaps = 359 segments) — every segment's final episode of a setup is correctly excluded from the inter-episode gap distribution rather than being given a fabricated multi-day "inactivity" duration. This internal consistency between RE-1's independently-derived segment count and RE-2's own censoring counts is a correctness cross-check, not a new finding.

## 4. Strongest non-structural (empirical) overlaps

Excluding the four `SHARED_INPUTS_ONLY` pairs (below), the two genuinely `EMPIRICAL` pairs (no shared input facts at all) both show a real, moderate association:

- `sustained_displacement_streak` × `vwap_extension_with_volume_confirmation`: correlation 0.327, lift 6.00
- `liquidity_sweep_with_volume_confirmation` × `sustained_displacement_streak`: correlation 0.275, lift 7.46

Both are worth a dedicated RE-3 hypothesis if RE-3's scope extends to joint-setup conditioning, since neither is explainable by the setups' own definitions.

## 5. Structurally-adjacent (shared-input) relationships

The four `SHARED_INPUTS_ONLY` pairs (see `relationships.py` for the full per-pair proof) all show a real correlation, expected given the shared `volume_spike` or `displacement` input, but **none is `LOGICALLY_IMPLIED`** — no pair's detected=True forces the other's detected=True under every computable input:

- `displacement_with_volume_confirmation` × `sustained_displacement_streak`: correlation 0.542 (the single strongest pairwise correlation observed) — despite both reading `displacement`, one requires a same-bar `volume_spike` the other never checks, and the other requires a 2+ bar streak the first never checks; `202` of `sustained_displacement_streak`'s episodes are fully contained inside a `displacement_with_volume_confirmation` episode, `1,422` the other way, confirming these are related-but-distinct conditions, not a subset relationship.
- `displacement_with_volume_confirmation` × `vwap_extension_with_volume_confirmation`: correlation 0.608, driven entirely by the shared `volume_spike` requirement.
- `liquidity_sweep_with_volume_confirmation` × `vwap_extension_with_volume_confirmation`: correlation 0.564, same mechanism.
- `displacement_with_volume_confirmation` × `liquidity_sweep_with_volume_confirmation`: correlation 0.421, the weakest of the four shared-`volume_spike` pairs — `displacement` and `liquidity_sweep` are the two primary facts with the least structural relation to each other (per RE-1's own fact-hierarchy finding, only `rejection`/`reclaim` imply `liquidity_sweep`; `displacement` is unrelated to that family).

This is a real, empirically-confirmed distinction: sharing an input fact reliably produces *some* correlation, but the magnitude still varies meaningfully by which facts are actually shared and how the setups otherwise diverge — exactly the nuance amendment 5 required the relationship metadata to preserve rather than collapsing "shares an input" into an implied-relationship label.

## 6. Transitions

**Same-setup and cross-setup recurrence are not mutually exclusive.** A next ActivationEvent can be multi-label (two or more setups tied on the identical bar), and when it includes both the originating setup and at least one other, that single transition counts toward both rates independently — their sum can exceed 100% for a given setup, and does (e.g. `liquidity_sweep_with_volume_confirmation`: 48.4% + 97.5% = 145.9%). See `RE2_Setup_Transitions.md`'s own recurrence-rate note and transition-matrix denominator table for the full mechanics.

`vwap_extension_with_volume_confirmation` has the highest same-setup recurrence (80.5% of its episodes are followed, within the same segment, by a next ActivationEvent that includes itself) — consistent with it being the highest-frequency, most persistent-feeling setup in this baseline. `sustained_displacement_streak` has the lowest same-setup recurrence (3.9%) despite a very high cross-setup recurrence (98.1%) — once a streak ends, another 2+ bar streak is slow to re-form, but *some* other setup fires again almost immediately. This mirrors §3's clustering finding from a different angle (episode-level next-event structure rather than raw gap timing).

The by-session breakdown shows `displacement_with_volume_confirmation`'s own self-transition probability is notably higher in RTH (40.8%) than OVERNIGHT (34.6%), while `vwap_extension`'s self-transition is comparable across both sessions (44.0% RTH vs 45.8% OVERNIGHT) — a session-dependent structural difference between these two setups worth carrying into any RE-3 session-conditioned design.

## 7. Data-quality caveats

Full detail: `RE1_ExpandedRun_Manifest.md` / `docs/market_engine/re1-5file-phase3-certification-report.md` (RE-1's own certification findings, reused here rather than re-derived).

- **ATR-warmup propagates into two setups' computability, exactly as expected**: `displacement_with_volume_confirmation` and `vwap_extension_with_volume_confirmation` both show 39 `atr is not present` insufficient-data bars — the same 3-cluster, 13-bar-each pattern RE-1's certification already root-caused as legitimate per-file-export `ta.atr` warmup, now confirmed to propagate correctly (not silently absorbed or hidden) into every setup that transitively depends on `displacement` or `vwap_relationship`.
- **A smaller, distinct `volume_ratio`-null count (18 bars) appears in every `volume_spike`-dependent setup** (`displacement_with_volume_confirmation`, `liquidity_sweep_with_volume_confirmation`, `vwap_extension_with_volume_confirmation`) — a different count from the 39-bar ATR cluster, so a different (unidentified) subset of bars. No root cause is established for this count in RE-1 or RE-2; nothing beyond "18 bars exist and are distinct from the ATR cluster" is asserted here. This is a targeted, unresolved data-quality follow-up required before RE-3 depends on precise `volume_spike` computability counts — it does not block RE-2 or UI v2, since RE-2's own reports (RE2_Setup_Profile.md's computability tables) already surface the count transparently rather than hiding it.
- **`liquidity_sweep_with_volume_confirmation`'s window-warmup insufficient-data count (718 = 359+359) exactly matches RE-1's own `liquidity_sweep` fact insufficient-data count** (`RE1_Fact_Profile.md`: 718) and the certified 359-segment count (2 window-warmup bars × 359 segments) — a correctness cross-check confirming RE-2's per-segment Rule/Setup Engine evaluation reproduces RE-1's own established numbers exactly.
- `trend_1m`'s pre-2025-07-20 unreliability (RE-1's certification finding) has no bearing on RE-2 — none of the 4 registered setups reads `trend_1m` (only `trend_5m` and the other 5 registered facts feed any setup's `required_facts`).
- The formal RE-1 certification verdict for this dataset remains REJECTED (one FAIL: `trend_1m`, outside RE-2's scope) — carried forward unchanged, not re-adjudicated here.

## 8. Implications for RE-3

- The four shared-`volume_spike` pairs' correlations (0.421–0.608) establish a real baseline "expected" correlation range for any two setups sharing that one input; any future setup pair correlating far outside that band (regardless of shared inputs) would be a more notable empirical finding than anything found in this baseline.
- `sustained_displacement_streak`'s low same-setup recurrence (§6) combined with its comparatively long inter-episode gaps (§3, median 140 minutes) suggests RE-3 should not assume a uniform "setups re-cluster quickly" prior across all four setups — the four have measurably different persistence/recurrence characters.
- Every setup's episode-count and duration distribution should be treated as dominated by single-bar events (§1) — an RE-3 design that implicitly assumes multi-bar setup episodes are typical would be modeling against this baseline's own evidence.
- The unresolved `volume_ratio`-null caveat (§7) should be either root-caused or explicitly bounded before RE-3 builds anything that depends on precise `volume_spike` computability counts.

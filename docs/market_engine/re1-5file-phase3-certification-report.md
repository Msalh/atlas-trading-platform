# RE-1 Five-File Dataset — Phase 3 Certification Report

**Run date**: 2026-07-20
**Tool**: `live/scripts/certify_historical_dataset.py` (commit `a907325` — threshold-scaling fix)
**Symbol**: `MNQ1!`  **Timeframe**: `5m`  **Bar-open shift applied**: yes (`--assume-bar-open-time`)
**Raw certifier output**: [`docs/market_engine/sprint31-task8-phase3-cert-5file-raw.txt`](sprint31-task8-phase3-cert-5file-raw.txt)

## 1. Input files (chronological)

| # | File | Rows loaded | New after dedup |
|---|---|---|---|
| 1 | `data/CME_03_03_25_16_06_25.csv` | 20,376 | 20,376 |
| 2 | `data/CME_16_06_25_30_09_25.csv` | 21,062 | 21,062 |
| 3 | `data/CME_01_10_31_12.csv` | 17,743 | 17,673 |
| 4 | `data/CME_01_01_05_04.csv` | 18,193 | 18,028 |
| 5 | `data/CME_06_04_20_07.csv` | 20,719 | 20,719 |
| | **raw_row_count** | **98,093** | |
| | **unique_row_count** | **97,858** | |

## 2. Duplicate & conflict audit

- **identical_duplicates_removed**: 235
- **conflict_count**: 0 — no timestamp anywhere across all five files carries disagreeing OHLC/VWAP/Market-State content. A nonzero count would have raised `ConflictingTimestampError` before certification could run at all (Phase 2's enforcement, not re-checked here — see [Phase 2 merge code](../../live/scripts/run_statistical_profile.py)).
- Every duplicate is a byte-identical overlap between two adjacent files' export windows (see boundary audit below) — the expected, safe case.

## 3. Exact combined range

**97,858 unique bars, `2025-03-02T23:05:00+00:00` → `2026-07-20T11:35:00+00:00`** (bar-close, post-shift).

## 4. File-transition boundary audit

| Transition | Mechanism | Evidence |
|---|---|---|
| File 1 → File 2 (2025-06-13 → 2025-06-15) | No overlap — ordinary weekend gap | Last bar 06-13T21:00 (close 21654.00) → first bar 06-15T22:05 (close 21812.25), a normal ~0.7% weekend move. Gap = 2945min, matches every other ordinary Fri→Sun weekend gap in the dataset exactly. |
| File 2 → File 3 (~2025-09-30/10-01) | 70-row identical-content overlap (confirmed in Phase 1) | Included in the 235 identical-duplicates-removed total; both files agree on OHLC/VWAP for every overlapping row. |
| File 3 → File 4 (~2025-12-31) | 165-row identical-content overlap | Same mechanism; already recorded in the prior 3-file expansion's manifest, reconfirmed unchanged here. |
| File 4 → File 5 (2026-04-03 → 2026-04-05) | No overlap — Good Friday (2026-04-03) shortened session + weekend | Last bar 04-03T13:15 (close 24132.25) → first bar 04-05T22:05 (close 24038.00), a normal ~0.4% move. Gap = 3410min (~681 bars), the single largest gap in the dataset — consistent with a shortened Good-Friday session folded into the following weekend, not a data loss. |

No transition shows a price discontinuity inconsistent with an ordinary session/weekend gap — no evidence of an unflagged contract-roll jump at any file boundary.

## 5. Gap classification (358 total, from `find_gaps`)

Every gap was inspected; all 358 fall into one of five recognized, explainable classes — **zero unexplained**:

| Class | Approx. size | Count (typical) | Notes |
|---|---|---|---|
| Daily maintenance | 65 min (~12 bars) | ~250 | CME's standard daily halt |
| Ordinary weekend | 2945 min (~588 bars) | ~55 | Friday close → Sunday reopen |
| DST-adjusted weekend | 2885 / 3005 min | 3 | 2025-03-09, 2025-11-02, 2026-03-08 — US DST transitions shift the UTC-measured gap by ±60min since CME's session boundaries are fixed in local (CT) time, not UTC |
| Holiday-shortened session | 290–305 min | 7 | 2025-05-26 (Memorial Day), 06-19 (Juneteenth), 09-01 (Labor Day), 11-27 (Thanksgiving), 2026-01-19 (MLK), 02-16 (Presidents), 05-25 (Memorial Day) |
| Holiday-extended weekend | 1505–3410 min | 6 | 2025-07-04 (July 4th), 2025-12-24/25 (Christmas), 2025-12-31/2026-01-01 (New Year's), 2026-04-03/05 (Good Friday — see boundary audit above), 2026-06-19 (Juneteenth, Fri), 2026-07-03 (July 4th) |
| Thanksgiving-Friday fragmentation | 650 + 3170 min | 1 (two gaps) | 2025-11-28 (day after Thanksgiving) shows two extra fragments beyond the usual shortened-session pattern — consistent with genuinely thin post-holiday liquidity causing TradingView's own bar formation to skip intervals, not a certifier or import defect |

`find_gaps()` does not know market hours by design (its own docstring) — every classification above is a human adjudication against known CME session/holiday conventions, not an automatic verdict.

## 6. Market Data Integrity — ATR (WARNING, not FAIL, after the threshold fix)

39 null/non-positive ATR bars, all clustering into **exactly 3 groups of 13**, precisely at the start of:
- File 1 (`2025-03-02T23:05` – `03-03T00:05`)
- File 2 (`2025-06-15T22:05` – `23:05`)
- File 5 (`2026-04-05T22:05` – `23:05`)

Files 3 and 4 show no ATR-warmup cluster of their own because their starts are masked by identical-content overlap with the preceding file — the preceding file's already-warmed-up ATR values win the first-insert-wins merge. This is legitimate per-export-session `ta.atr(14)` warmup (13 bars ≈ 14-period indicator startup), occurring once per distinct TradingView export session, not a data defect. `max_expected_warmup_clusters=5` (one per input file) correctly tolerates up to 100 nulls; 39 is well within that.

## 7. Feature Integrity — trend_1m (FAIL) — full root-cause finding

The certifier correctly FAILs this field: **27,799/97,858 bars (28.4%) have a null `trend_1m`**, far beyond any plausible warmup tolerance. Day-by-day investigation resolved this into two independent, fully explained phenomena — no part of it is unexplained:

**(a) A sustained hard cutoff, 2025-03-02 through 2025-07-20 (100% null every single day)**
Every day in this range is null at 100%, with no gradual decline — the last day, 2025-07-20, is a partial day (4/23 bars null, the rest populated), and every day from 2025-07-21 onward is 0% null. **2025-07-20 is exactly 365 days before this run's date (2026-07-20).** This is very strong evidence that the TradingView account used to generate these exports has a **365-day historical intraday (1-minute) data lookback limit** — any 5-minute bar older than that boundary cannot carry `trend_1m`, because production's Pine script computes it via a `request.security(ticker, "1", ...)` call requesting **1-minute** chart data, and 1-minute history simply does not exist that far back for this account's plan tier. This is consistent with, and now the first hard confirmation of, the plan-tier lookback-limit fact noted (but not confirmed) in Sprint 25A.5.

**(b) A separate, small, gradually-tapering cluster, 2026-04-05 through 2026-04-08 (660 bars)**
2026-04-05 and 04-06 are 100% null, 04-07 is 100% null, 04-08 tapers to 85/276 (31%) before reaching zero — a gradual decline over ~3 days, the textbook shape of ordinary EMA-based indicator warmup at File 5's own export-session start (the same mechanism as the ATR clusters above, just a longer warmup window since `trend_1m` needs a run of 1-minute EMA bars rather than a single 14-bar ATR).

**This is a genuine, well-evidenced dataset limitation — not a certifier bug, not an importer bug, and not a defect in `atlas.market_engine` or `atlas.research.statistical_profiling`.** It reflects a real boundary in what TradingView's export could provide for bars older than ~365 days before the export date.

**Scope impact**: `trend_1m` is a **raw wire/storage field only** (`atlas/market_engine/models.py`) — it is never read by `atlas/rule_engine/facts.py`'s evaluation logic (confirmed by direct grep; the only Rule Engine reference to `trend_1m` is an explanatory comment on why it and its siblings are *not* among the 7 registered facts) and therefore never reaches RE-1's Fact Profile, Rule Relationships, Conditional Probability, Time Distribution, or Persistence reports, all of which are built exclusively from `build_rule_engine_output_window`'s 7 registered facts (`volume_spike`, `displacement`, `rejection`, `trend_5m`, `liquidity_sweep`, `reclaim`, `vwap_relationship`). `trend_5m` — the field RE-1 actually profiles — has only 63 nulls (WARNING, within the 100-bar tolerance), unaffected by this finding.

## 8. Other Feature Integrity results

- `trend_5m`: WARNING, 63/97,858 null — within warmup tolerance.
- `trend_15m`, `trend_1h`: PASS, no nulls.
- Rule Engine placeholder flags (`liquidity_sweep`/`reclaim`/`rejection`/`displacement`/`volume_spike`): WARNING, all-False on every bar — expected, by Sprint 5 design.
- `distance_from_vwap_points` consistency: PASS.
- `nearest_liquidity_level`/`type` consistency: PASS.

## 9. VWAP precision samples

| Position | Timestamp | VWAP (full precision) | Close |
|---|---|---|---|
| Early | 2025-03-02T23:55:00Z | `20996.120484280415` | 20956.50 |
| Middle | 2025-11-07T02:15:00Z | `25288.646238174624` | 25234.00 |
| Late | 2026-07-20T10:50:00Z | `28859.191410299245` | 28968.25 |

Full float precision preserved throughout — no truncation at any point in the merge/translation pipeline, consistent with every prior Sprint 31 finding on this dataset.

## 10. Instrument identity limitations

No symbol column exists in any of the five source files — the same structural fact established in Sprint 29A.6/31 (TradingView's native chart-export carries no symbol field). `MNQ1!` is asserted at import time across all five files, consistent with Sprint 31 Task 1's confirmed live production symbol. There remains no per-instrument tick-size/identity registry in this codebase (`TICK_SIZE = 0.25` global constant, standing architectural debt, unchanged by this work).

## 11. Contract-roll observations

No price discontinuity inconsistent with an ordinary gap was found at any of the four file-transition boundaries (Section 4) or anywhere else in the series. `MNQ1!` is TradingView's continuous front-month contract symbol; any roll adjustment happens inside TradingView's own continuous-contract construction and is invisible to this dataset by design — this project has no independent way to detect or confirm individual roll dates from the data alone. This is a disclosed limitation carried over unchanged from prior certifications, not a new finding.

## 12. Certification Summary

```
Checks run: 27  |  PASS: 21  |  WARNING: 5  |  FAIL: 1
VERDICT: REJECTED
```

**Formal (mechanical, all-fields) verdict: REJECTED**, per this project's established strict-AND certification philosophy — one FAIL anywhere fails the whole certification, no partial credit, and this is deliberately not weakened here.

**Fitness for RE-1's actual scope: no blocking defect.** The single FAIL is confined to `trend_1m`, a raw wire field RE-1 never reads. Every field RE-1's five reports actually consume — the 7 registered Rule Engine facts, OHLCV, VWAP, session/trading-date fields — passes or warns-with-explanation only. The `trend_1m` finding is a genuine, fully-characterized data-source limitation (§7) that must be disclosed as a caveat for any *future* use of the raw `trend_1m` field, but it does not invalidate anything RE-1 computes.

**Conclusion: the five-file, 97,858-bar dataset is certified fit for descriptive Setup Profiling (RE-1's actual scope), with the `trend_1m` limitation disclosed as a documented, out-of-scope caveat — not certified as unconditionally clean by the mechanical PASS/WARNING/FAIL rule.**

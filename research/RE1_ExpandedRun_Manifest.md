# RE-1 Expanded Dataset — Manifest & Pre-Import Validation Report

**Run date**: 2026-07-20
**Code version**: `faacf83cf2ac43c8ac4182629d75a5540bc7215f`
**Symbol**: `MNQ1!`  **Timeframe**: `5m`  **Bar-open shift applied**: yes (`--assume-bar-open-time`, same convention Sprint 31 Task 3 established for this data source)

## Source files (as given vs. as found)

One filename did not exist as typed: `data/CME_01_01_0_04.csv` was requested; the actual file is `data/CME_01_01_05_04.csv` (a digit differs). Proceeded with the real file, flagged rather than guessed.

| # | File | Row count |
|---|---|---|
| 1 | `data/CME_01_10_31_12.csv` | 17,743 |
| 2 | `data/CME_01_01_05_04.csv` | 18,193 |
| 3 | `data/CME_06_04_20_07.csv` | 20,719 |
| | **Sum (pre-dedup)** | **56,655** |
| | **Unique after dedup** | **56,490** |
| | **Duplicate rows removed** | **165** |

## Per-file inspection (items 1-8)

| File | First timestamp (bar-open, raw) | Last timestamp (bar-open, raw) | Symbol column | Timeframe (inferred) | Required columns | Bar-open confirmed? | Malformed/truncated trailing rows |
|---|---|---|---|---|---|---|---|
| CME_01_10_31_12.csv | 2025-09-30T15:05:00Z | 2025-12-31T21:50:00Z | none present (structural - see below) | 5m (300s modal delta) | all 27, identical header to the certified dataset | inferred, not freshly re-verified (see below) | none - 0 malformed, last 3 rows complete |
| CME_01_01_05_04.csv | 2025-12-31T08:10:00Z | 2026-04-03T13:10:00Z | none present | 5m | all 27, identical | inferred | none |
| CME_06_04_20_07.csv | 2026-04-05T22:00:00Z | 2026-07-20T11:30:00Z | none present | 5m | all 27, identical | inferred | none |

- **Symbol/instrument identity (item 4)**: no symbol column exists in any of the three files — the same structural fact established in Sprint 29A.6/31 (TradingView's native chart-export carries no symbol field; `plot()` cannot carry strings). Symbol is asserted at import time (`MNQ1!`), consistent with Task 1's confirmed live production symbol.
- **Bar-open confirmation (item 7)**: **inferred, not freshly independently re-verified.** No live production data exists for Sept 2025-Apr 2026 to run Task 3's field-by-field comparison against, so this specific claim rests on the already-proven, mechanism-level fact from Sprint 31 Task 3: TradingView's native CSV export always reports bar-open time, platform-wide, independent of any per-export session. Applying `--assume-bar-open-time` here is a reasoned extension of that proof, not a fresh one — flagged explicitly rather than silently assumed.

## Overlaps and gaps between files (item 9) — corrects the stated expectation

**File 1 ↔ File 2**: genuine overlap, not previously mentioned in the task description. 165 rows, `2025-12-31T08:10:00Z → 2025-12-31T21:50:00Z`. All 165 overlapping rows are byte-identical between the two files (OHLC, VWAP checked) — safe for repository dedup with zero data loss.

**File 2 ↔ File 3**: **no overlap** — contrary to the stated expectation of "overlap around 2026-04-06." What actually exists is a gap: File 2 ends Friday 2026-04-03T13:15:00Z (bar-close), File 3 begins Sunday 2026-04-05T22:05:00Z. This is **not** an ordinary weekend gap — a normal Friday CME equity-index close is ~21:00-22:00 UTC, not 13:15 UTC. The data strongly suggests **2026-04-03 is Good Friday** (Easter 2026 falls April 5), a day CME equity index futures typically trade a shortened session — consistent with File 2's data stopping mid-morning rather than at a normal close. This is a plausible, well-supported explanation, not independently confirmed against an external holiday calendar in this session — worth your own confirmation.

**File 3 ↔ already-imported certified dataset**: File 3 fully contains all 1200 rows of the already-imported `data/CME_MINI_MNQ.csv` (Sprint 31 Phase 3), byte-identical, `2026-07-13T13:00:00Z → 2026-07-17T20:55:00Z` (bar-open). **This means Phase B's real apply of File 3 will show substantially fewer than 20,719 new inserts** — at minimum 1200 duplicates from the already-certified import, plus however many rows collide with live production ingestion that has been running continuously since (Sprint 31 Phase 3's own first apply already showed 773 unexpected pre-existing duplicates in just the July 13-17 window alone).

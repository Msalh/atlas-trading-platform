# Sprint 31 Task 3 — Historical ↔ Live Equivalence Certification Report

**Date evaluated**: 2026-07-20
**Symbol**: `MNQ1!` (confirmed live production symbol, Task 1) · **Timeframe**: `5m`
**Inputs**: a fresh TradingView historical CSV export (`CME_MINI_MNQ1!, 5_6a6df.csv`) and three real production `GET /api/v1/market-state/export?start=T&end=T` response bodies, for `2026-07-20T07:50:00Z`, `08:00:00Z`, `08:10:00Z`.
**Tool**: `scripts/verify_historical_live_equivalence.py` (commit `263fd6104324572d9c95245de472ee3f8726e72b`, extended in this report's commit with `--assume-bar-open-time`).

## 1. Initial finding: raw comparison fails

Comparing each API timestamp directly against the CSV row at the identical timestamp fails on every OHLC/VWAP/ATR/Volume field, at all three samples (see `raw_comparison` below). Manual cross-reference against the raw CSV showed the API event at `T` matches the CSV row at `T − 5min` exactly:

- API `07:50:00Z` ⇔ CSV `07:45:00Z` (epoch `1784533500`)
- API `08:00:00Z` ⇔ CSV `07:55:00Z` (epoch `1784534100`)
- API `08:10:00Z` ⇔ CSV `08:05:00Z` (epoch `1784534700`)

A consistent, systematic 5-minute (one bar) offset across all three independent samples.

## 2. Root cause investigation

**Live webhook** (`pine/MNQU6_market_state_v1.pine:202-209`): `isoTimestamp` — and therefore the wire `timestamp`/`event_id` — is built from `time_close`, deliberately: "the bar's close time - it just closed, this is when the event happened" (the script's own docstring).

**Historical export CSV**: the CSV's native `time` column is **not** produced by anything in `pine/MNQU6_market_state_v1_historical_export.pine` — there is no `plot()` call for it anywhere in that file. It is TradingView's own automatic "Download chart data" export column, which is populated from Pine's `time` builtin (bar-**open** time), TradingView's platform default — entirely independent of, and never overridden by, either Pine script.

**Conclusion**: this is classification **(2) — a TradingView CSV export timestamp convention**, not a project decision and not a bug. The live webhook has always deliberately used `time_close`; the CSV export has always used TradingView's platform-default bar-open `time`, completely outside this project's control. Neither the live Pine payload nor `atlas.market_engine.adapters.tradingview.translator.to_canonical()` is at fault — both function exactly as designed. This is precisely the scenario `import_historical_market_state_csv.py`'s pre-existing `--assume-bar-open-time` flag was built for (added Sprint 25B, never previously confirmed necessary until this real comparison).

## 3. Normalization applied

`scripts/verify_historical_live_equivalence.py` gained a `--assume-bar-open-time` flag that threads `cadence_minutes` into `import_historical_market_state_csv.py`'s own `build_candidates`/`row_to_raw_json` — the same existing mechanism, not a reimplementation. This is a one-directional, deterministic, single-bar-duration shift, applied only because the raw comparison in Section 1 empirically proved it necessary — never applied speculatively.

## 4. Normalized comparison result

With `--assume-bar-open-time`, all three samples:

| Field | 07:50 | 08:00 | 08:10 |
|---|---|---|---|
| Open, High, Low, Close | PASS | PASS | PASS |
| Volume | PASS | PASS | PASS |
| Nearest Liquidity Level / Type | PASS | PASS | PASS |
| Trend 1m/5m/15m/1h | PASS | PASS | PASS |
| Liquidity Sweep/Reclaim/Rejection/Displacement/Volume Spike | PASS (trivially-constant, see tool notes) | PASS | PASS |
| VWAP | **FAIL** | **FAIL** | **FAIL** |
| ATR | **FAIL** | **FAIL** | **FAIL** |
| Volume Ratio | **FAIL** | **FAIL** | **FAIL** |
| Distance From VWAP | **FAIL** | **FAIL** | **FAIL** |

Full tool output for both runs is in `sprint31-task3-evidence/raw_comparison_output.txt` and `sprint31-task3-evidence/normalized_comparison_output.txt`, alongside this report.

## 5. Characterizing the residual mismatch

The bar-open/bar-close normalization resolved event identity completely — OHLC, Volume, Trend, and Liquidity fields are exact matches on every sample. The four remaining failing fields (VWAP, ATR, Volume Ratio, Distance From VWAP) are all continuous, Pine-computed analytical values (never tick-validated — see Sprint 26). Quantifying the actual differences:

| Field (sample) | Historical (CSV) | Live (API) | Absolute diff | Relative diff |
|---|---|---|---|---|
| VWAP (07:50) | 28849.31047566075 | 28849.3104756607 | 5.09e-11 | 1.77e-15 |
| ATR (07:50) | 32.32920010001545 | 32.3292001 | 1.55e-11 | 4.78e-13 |
| Volume Ratio (07:50) | 0.9281594740351656 | 0.928159474 | 3.52e-11 | 3.79e-11 |
| Distance From VWAP (07:50) | 38.689524339250056 | 38.6895243393 | 4.99e-11 | 1.29e-12 |
| (08:00, 08:10 samples) | — | — | 1e-12 to 5e-11 | 1e-15 to 5e-11 |

Every difference sits in the last one or two significant digits of a ~15-16-digit double-precision float — at or below the practical text-serialization noise floor. The live JSON value consistently carries **one fewer** significant digit than the CSV value (e.g. `32.3292001` vs `32.32920010001545`), consistent with Pine's `str.tostring()` (used by `f_num()` for the live `alert()` payload) formatting to fewer significant digits than TradingView's CSV chart-export formatter — a text-serialization difference between two different TradingView output codepaths, not a difference in the underlying computed value, and not a translation defect (both sides pass through the identical `to_canonical()` unchanged).

## 6. Final status

**Task 3 — Historical ↔ Live Equivalence: FAIL**, under the tool's documented standard (exact equality, no tolerance — established explicitly in this Sprint and never relaxed here).

This is reported honestly as a FAIL, not softened to a PASS, per instruction. It is not, however, the FAIL described by "the live and historical pipelines assign genuinely different event identities" — identity is conclusively confirmed once the timestamp convention is accounted for (OHLC/Volume/Trend/Liquidity all match exactly). The residual failure is confined to four analytical fields, at a magnitude (~1e-11 to 1e-15 relative) consistent with a benign text-serialization precision difference between TradingView's own CSV-export and live-alert formatting paths — not a data-corruption or mistranslation defect requiring a code fix.

No production code was changed — this is not a translator, wire-model, or Pine defect. No new tolerance was added to the tool without being asked; the strict standard stands as documented, and this finding was reported for a human decision rather than silently accommodated.

## 7. Disposition

Decision: **accepted as a documented caveat, not a blocker** — the same treatment Sprint 31 Task 4's three WARNINGs received. Event identity is confirmed (OHLC/Volume/Trend/Liquidity exact matches); the residual ~1e-11-to-1e-15-relative mismatch on VWAP/ATR/Volume Ratio/Distance From VWAP is explained, quantified, and attributed to a TradingView text-serialization difference between its live-alert and CSV-export codepaths, not a data-identity or translation defect. Task 3 is closed on this basis. The tool's zero-tolerance standard remains unchanged in code — this is a recorded human judgment call about this specific, already-quantified finding, not a relaxation of the comparison itself.

**Task 3 status: CLOSED.**

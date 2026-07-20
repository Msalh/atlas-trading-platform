# RE-2 Setup Profile

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T14:04:22.064038+00:00
- **Code version**: 74608b58452e92c07bcda4bb55b62c4ded4c589c

Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate content. trend_1m is never used - it is not a registered Rule Engine fact.

## displacement_with_volume_confirmation

- Computable bars: 97801  Active bars: 7786 (8.0%)
- Episode count: 5270  (left-censored: 33, right-censored: 2, fully observed: 5235)
- Single-bar episodes: 3939  Multi-bar episodes: 1331
- Activation bars: 5270  Continuation bars: 2516
- Eligible trading days: 433  Episodes/trading day: 12.17
- Days with >=1 activation: 427 (98.6%)

**All observed episodes** (n=5270) duration (bars): mean=1.48 median=1.00 p75=2.00 p90=3.00 p95=4.00 max=10.00
**Fully observed (non-censored) episodes only** (n=5235) duration (bars): mean=1.48 median=1.00 p75=2.00 p90=3.00 p95=4.00 max=10.00

## liquidity_sweep_with_volume_confirmation

- Computable bars: 97089  Active bars: 5263 (5.4%)
- Episode count: 2970  (left-censored: 0, right-censored: 2, fully observed: 2968)
- Single-bar episodes: 1776  Multi-bar episodes: 1194
- Activation bars: 2970  Continuation bars: 2293
- Eligible trading days: 433  Episodes/trading day: 6.86
- Days with >=1 activation: 419 (96.8%)

**All observed episodes** (n=2970) duration (bars): mean=1.77 median=1.00 p75=2.00 p90=3.00 p95=4.00 max=11.00
**Fully observed (non-censored) episodes only** (n=2968) duration (bars): mean=1.77 median=1.00 p75=2.00 p90=3.00 p95=4.00 max=11.00

## sustained_displacement_streak

- Computable bars: 97463  Active bars: 3021 (3.1%)
- Episode count: 1708  (left-censored: 0, right-censored: 4, fully observed: 1704)
- Single-bar episodes: 1082  Multi-bar episodes: 626
- Activation bars: 1708  Continuation bars: 1313
- Eligible trading days: 433  Episodes/trading day: 3.94
- Days with >=1 activation: 393 (90.8%)

**All observed episodes** (n=1708) duration (bars): mean=1.77 median=1.00 p75=2.00 p90=4.00 p95=5.00 max=9.00
**Fully observed (non-censored) episodes only** (n=1704) duration (bars): mean=1.77 median=1.00 p75=2.00 p90=4.00 p95=5.00 max=9.00

## vwap_extension_with_volume_confirmation

- Computable bars: 97801  Active bars: 11467 (11.7%)
- Episode count: 6331  (left-censored: 10, right-censored: 2, fully observed: 6319)
- Single-bar episodes: 3958  Multi-bar episodes: 2373
- Activation bars: 6331  Continuation bars: 5136
- Eligible trading days: 433  Episodes/trading day: 14.62
- Days with >=1 activation: 432 (99.8%)

**All observed episodes** (n=6331) duration (bars): mean=1.81 median=1.00 p75=2.00 p90=3.00 p95=5.00 max=14.00
**Fully observed (non-censored) episodes only** (n=6319) duration (bars): mean=1.81 median=1.00 p75=2.00 p90=3.00 p95=5.00 max=14.00

## Computability evidence

| setup | total bars | computable | non-computable | detected true | detected false |
|---|---|---|---|---|---|
| displacement_with_volume_confirmation | 97858 | 97801 | 57 | 7786 | 90015 |
| liquidity_sweep_with_volume_confirmation | 97858 | 97089 | 769 | 5263 | 91826 |
| sustained_displacement_streak | 97858 | 97463 | 395 | 3021 | 94442 |
| vwap_extension_with_volume_confirmation | 97858 | 97801 | 57 | 11467 | 86334 |

**displacement_with_volume_confirmation insufficient-data reasons**:
  - 39x: displacement is insufficient_data: atr is not present on this MarketState
  - 18x: volume_spike is insufficient_data: volume_ratio is not present on this MarketState

**liquidity_sweep_with_volume_confirmation insufficient-data reasons**:
  - 359x: liquidity_sweep is insufficient_data: fewer than 3 bars available in the window (got 1)
  - 359x: liquidity_sweep is insufficient_data: fewer than 3 bars available in the window (got 2)
  - 51x: volume_spike is insufficient_data: volume_ratio is not present on this MarketState

**sustained_displacement_streak insufficient-data reasons**:
  - 359x: fewer than 2 bars available in history (got 1)
  - 36x: displacement is insufficient_data on the current bar: atr is not present on this MarketState

**vwap_extension_with_volume_confirmation insufficient-data reasons**:
  - 39x: vwap_relationship is insufficient_data: atr is not present on this MarketState
  - 18x: volume_spike is insufficient_data: volume_ratio is not present on this MarketState

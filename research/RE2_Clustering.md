# RE-2 Clustering

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T14:04:22.064038+00:00
- **Code version**: 74608b58452e92c07bcda4bb55b62c4ded4c589c

Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate content. trend_1m is never used - it is not a registered Rule Engine fact.

Inter-episode time is computed only within the same market-data segment (never bridging a maintenance/weekend/holiday gap). An episode with no within-segment successor is counted as `censored_by_gap`, not given a fabricated inactivity duration. No certified maintenance/weekend/holiday classifier exists as reusable code in this project (only as prose in a certification report), so segment-boundary gaps are reported as raw duration with the generic label `segment_boundary`, not re-classified here.

## displacement_with_volume_confirmation

- Within-segment inter-episode gaps: 4911  Censored by gap (no within-segment successor): 359
- Gap minutes (n=4911): mean=78.60 median=45.00 p75=110.00 p90=200.00 p95=270.00 max=755.00
- Episodes/trading day: 12.17

**Repeat activation within N minutes** (count of within-segment gaps <= N):
  - <= 15min: 1187
  - <= 30min: 1998
  - <= 60min: 3005
  - <= 120min: 3890

**Burst/cluster sizes, reported at every threshold (no single canonical choice)**:
  - threshold <= 15min: 4083 bursts, longest=7 episodes; sizes: [1, 1, 2, 1, 3, 2, 2, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1...]
  - threshold <= 30min: 3272 bursts, longest=8 episodes; sizes: [1, 1, 6, 2, 3, 3, 2, 1, 1, 2, 1, 2, 1, 3, 4, 2, 2, 1, 1, 3...]
  - threshold <= 60min: 2265 bursts, longest=10 episodes; sizes: [1, 1, 6, 2, 3, 3, 2, 2, 2, 3, 1, 7, 2, 2, 1, 4, 1, 5, 1, 1...]

## liquidity_sweep_with_volume_confirmation

- Within-segment inter-episode gaps: 2613  Censored by gap (no within-segment successor): 357
- Gap minutes (n=2613): mean=120.72 median=60.00 p75=165.00 p90=330.00 p95=405.00 max=1165.00
- Episodes/trading day: 6.86

**Repeat activation within N minutes** (count of within-segment gaps <= N):
  - <= 15min: 639
  - <= 30min: 1000
  - <= 60min: 1368
  - <= 120min: 1782

**Burst/cluster sizes, reported at every threshold (no single canonical choice)**:
  - threshold <= 15min: 2331 bursts, longest=6 episodes; sizes: [1, 1, 2, 1, 1, 1, 1, 1, 1, 2, 1, 1, 3, 1, 1, 3, 3, 1, 3, 2...]
  - threshold <= 30min: 1970 bursts, longest=8 episodes; sizes: [1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 1, 3, 1, 1, 3, 3, 1, 5, 1, 4...]
  - threshold <= 60min: 1602 bursts, longest=9 episodes; sizes: [1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 4, 2, 3, 3, 1, 5, 1, 4, 1, 2...]

## sustained_displacement_streak

- Within-segment inter-episode gaps: 1349  Censored by gap (no within-segment successor): 359
- Gap minutes (n=1349): mean=189.24 median=140.00 p75=315.00 p90=390.00 p95=475.00 max=950.00
- Episodes/trading day: 3.94

**Repeat activation within N minutes** (count of within-segment gaps <= N):
  - <= 15min: 124
  - <= 30min: 268
  - <= 60min: 439
  - <= 120min: 639

**Burst/cluster sizes, reported at every threshold (no single canonical choice)**:
  - threshold <= 15min: 1584 bursts, longest=3 episodes; sizes: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1...]
  - threshold <= 30min: 1440 bursts, longest=5 episodes; sizes: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1...]
  - threshold <= 60min: 1269 bursts, longest=5 episodes; sizes: [1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 1, 1, 3, 1, 1, 1, 1...]

## vwap_extension_with_volume_confirmation

- Within-segment inter-episode gaps: 5972  Censored by gap (no within-segment successor): 359
- Gap minutes (n=5972): mean=65.01 median=35.00 p75=85.00 p90=165.00 p95=225.00 max=525.00
- Episodes/trading day: 14.62

**Repeat activation within N minutes** (count of within-segment gaps <= N):
  - <= 15min: 1684
  - <= 30min: 2891
  - <= 60min: 4063
  - <= 120min: 4991

**Burst/cluster sizes, reported at every threshold (no single canonical choice)**:
  - threshold <= 15min: 4647 bursts, longest=8 episodes; sizes: [1, 1, 1, 1, 2, 1, 2, 1, 1, 2, 2, 2, 1, 1, 1, 3, 1, 1, 1, 1...]
  - threshold <= 30min: 3440 bursts, longest=12 episodes; sizes: [2, 1, 4, 2, 2, 2, 4, 3, 3, 1, 1, 1, 1, 1, 2, 3, 2, 2, 1, 1...]
  - threshold <= 60min: 2268 bursts, longest=15 episodes; sizes: [2, 1, 8, 2, 4, 3, 3, 1, 1, 2, 1, 5, 2, 2, 1, 1, 1, 9, 1, 1...]

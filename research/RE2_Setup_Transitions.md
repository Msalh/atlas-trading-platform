# RE-2 Setup Transitions

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T14:04:22.064038+00:00
- **Code version**: 74608b58452e92c07bcda4bb55b62c4ded4c589c

Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate content. trend_1m is never used - it is not a registered Rule Engine fact.

Every transition points to the NEXT ActivationEvent (possibly multi-label, when two or more setups activate on the identical bar) - no ordering is invented among setups tied on the same bar. An episode with no qualifying next event before its segment ends is censored (never resolved across a data gap).

Total episode-level transitions: 16279  Censored: 762 (4.7%)

## Transition matrix (from setup -> to setup, expanding multi-label events)

| from | to | count | probability |
|---|---|---|---|
| displacement_with_volume_confirmation | vwap_extension_with_volume_confirmation | 3636 | 43.3% |
| displacement_with_volume_confirmation | displacement_with_volume_confirmation | 3014 | 35.9% |
| displacement_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 1472 | 17.5% |
| displacement_with_volume_confirmation | sustained_displacement_streak | 284 | 3.4% |
| liquidity_sweep_with_volume_confirmation | vwap_extension_with_volume_confirmation | 2306 | 42.3% |
| liquidity_sweep_with_volume_confirmation | displacement_with_volume_confirmation | 1567 | 28.8% |
| liquidity_sweep_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 1376 | 25.3% |
| liquidity_sweep_with_volume_confirmation | sustained_displacement_streak | 199 | 3.7% |
| sustained_displacement_streak | vwap_extension_with_volume_confirmation | 1073 | 41.1% |
| sustained_displacement_streak | displacement_with_volume_confirmation | 1019 | 39.0% |
| sustained_displacement_streak | liquidity_sweep_with_volume_confirmation | 459 | 17.6% |
| sustained_displacement_streak | sustained_displacement_streak | 62 | 2.4% |
| vwap_extension_with_volume_confirmation | vwap_extension_with_volume_confirmation | 4861 | 45.5% |
| vwap_extension_with_volume_confirmation | displacement_with_volume_confirmation | 3418 | 32.0% |
| vwap_extension_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 1944 | 18.2% |
| vwap_extension_with_volume_confirmation | sustained_displacement_streak | 455 | 4.3% |

## Recurrence rates

| setup | same-setup recurrence | cross-setup recurrence |
|---|---|---|
| displacement_with_volume_confirmation | 59.8% | 82.4% |
| liquidity_sweep_with_volume_confirmation | 48.4% | 97.5% |
| sustained_displacement_streak | 3.9% | 98.1% |
| vwap_extension_with_volume_confirmation | 80.5% | 75.4% |

## Transition matrix by session (at the FROM-episode's activation session)

### OVERNIGHT

| from | to | count | probability |
|---|---|---|---|
| displacement_with_volume_confirmation | vwap_extension_with_volume_confirmation | 2934 | 44.1% |
| displacement_with_volume_confirmation | displacement_with_volume_confirmation | 2302 | 34.6% |
| displacement_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 1227 | 18.4% |
| displacement_with_volume_confirmation | sustained_displacement_streak | 197 | 3.0% |
| liquidity_sweep_with_volume_confirmation | vwap_extension_with_volume_confirmation | 2023 | 43.3% |
| liquidity_sweep_with_volume_confirmation | displacement_with_volume_confirmation | 1286 | 27.5% |
| liquidity_sweep_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 1232 | 26.4% |
| liquidity_sweep_with_volume_confirmation | sustained_displacement_streak | 132 | 2.8% |
| sustained_displacement_streak | vwap_extension_with_volume_confirmation | 746 | 44.0% |
| sustained_displacement_streak | displacement_with_volume_confirmation | 609 | 35.9% |
| sustained_displacement_streak | liquidity_sweep_with_volume_confirmation | 314 | 18.5% |
| sustained_displacement_streak | sustained_displacement_streak | 27 | 1.6% |
| vwap_extension_with_volume_confirmation | vwap_extension_with_volume_confirmation | 4128 | 45.8% |
| vwap_extension_with_volume_confirmation | displacement_with_volume_confirmation | 2834 | 31.4% |
| vwap_extension_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 1723 | 19.1% |
| vwap_extension_with_volume_confirmation | sustained_displacement_streak | 328 | 3.6% |

### RTH

| from | to | count | probability |
|---|---|---|---|
| displacement_with_volume_confirmation | displacement_with_volume_confirmation | 712 | 40.8% |
| displacement_with_volume_confirmation | vwap_extension_with_volume_confirmation | 702 | 40.2% |
| displacement_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 245 | 14.0% |
| displacement_with_volume_confirmation | sustained_displacement_streak | 87 | 5.0% |
| liquidity_sweep_with_volume_confirmation | vwap_extension_with_volume_confirmation | 283 | 36.5% |
| liquidity_sweep_with_volume_confirmation | displacement_with_volume_confirmation | 281 | 36.3% |
| liquidity_sweep_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 144 | 18.6% |
| liquidity_sweep_with_volume_confirmation | sustained_displacement_streak | 67 | 8.6% |
| sustained_displacement_streak | displacement_with_volume_confirmation | 410 | 44.7% |
| sustained_displacement_streak | vwap_extension_with_volume_confirmation | 327 | 35.7% |
| sustained_displacement_streak | liquidity_sweep_with_volume_confirmation | 145 | 15.8% |
| sustained_displacement_streak | sustained_displacement_streak | 35 | 3.8% |
| vwap_extension_with_volume_confirmation | vwap_extension_with_volume_confirmation | 733 | 44.0% |
| vwap_extension_with_volume_confirmation | displacement_with_volume_confirmation | 584 | 35.1% |
| vwap_extension_with_volume_confirmation | liquidity_sweep_with_volume_confirmation | 221 | 13.3% |
| vwap_extension_with_volume_confirmation | sustained_displacement_streak | 127 | 7.6% |

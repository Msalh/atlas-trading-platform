# RE-1 Conditional Probability

> **VALIDATION RUN** - this report exists to prove the RE-1 pipeline computes correctly, not to characterize real market behavior. The dataset behind it (1200 bars) is a correctness-validation dataset, not a basis for any market-characteristics or trading conclusion. The same pipeline, unchanged, is designed to be re-run against a much larger historical dataset once one is available.

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2026-07-13T13:05:00+00:00 -> 2026-07-17T21:00:00+00:00
- **Source**: csv:../data/CME_MINI_MNQ.csv
- **Row count**: 1200
- **Generated at**: 2026-07-20T11:44:35.275973+00:00
- **Code version**: 1a97a859c72e2fbd1eed01bf891bf5c35ddd5f6c

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

P(target = target_value | condition = condition_value), over bars where both facts are computable. Exhaustive over every ordered pair of distinct registered facts.

## P(displacement | volume_spike)

| volume_spike = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 96.6% | 1043 |
| false | true | 3.4% | 1043 |
| true | false | 49.7% | 157 |
| true | true | 50.3% | 157 |

## P(rejection | volume_spike)

| volume_spike = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 96.8% | 1043 |
| false | true | 3.2% | 1043 |
| true | false | 94.3% | 157 |
| true | true | 5.7% | 157 |

## P(trend_5m | volume_spike)

| volume_spike = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 45.6% | 968 |
| false | flat | 24.0% | 968 |
| false | up | 30.5% | 968 |
| true | down | 47.4% | 137 |
| true | flat | 32.8% | 137 |
| true | up | 19.7% | 137 |

## P(liquidity_sweep | volume_spike)

| volume_spike = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 76.5% | 1033 |
| false | true | 23.5% | 1033 |
| true | false | 61.8% | 157 |
| true | true | 38.2% | 157 |

## P(reclaim | volume_spike)

| volume_spike = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 98.4% | 1033 |
| false | true | 1.6% | 1033 |
| true | false | 94.9% | 157 |
| true | true | 5.1% | 157 |

## P(vwap_relationship | volume_spike)

| volume_spike = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 31.8% | 1043 |
| false | extended_below | 46.1% | 1043 |
| false | within_band | 22.1% | 1043 |
| true | extended_above | 29.9% | 157 |
| true | extended_below | 47.8% | 157 |
| true | within_band | 22.3% | 157 |

## P(volume_spike | displacement)

| displacement = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 92.8% | 1086 |
| false | true | 7.2% | 1086 |
| true | false | 30.7% | 114 |
| true | true | 69.3% | 114 |

## P(rejection | displacement)

| displacement = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 96.4% | 1086 |
| false | true | 3.6% | 1086 |
| true | false | 97.4% | 114 |
| true | true | 2.6% | 114 |

## P(trend_5m | displacement)

| displacement = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 45.1% | 1006 |
| false | flat | 24.5% | 1006 |
| false | up | 30.4% | 1006 |
| true | down | 52.5% | 99 |
| true | flat | 31.3% | 99 |
| true | up | 16.2% | 99 |

## P(liquidity_sweep | displacement)

| displacement = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 75.9% | 1077 |
| false | true | 24.1% | 1077 |
| true | false | 61.9% | 113 |
| true | true | 38.1% | 113 |

## P(reclaim | displacement)

| displacement = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 98.5% | 1077 |
| false | true | 1.5% | 1077 |
| true | false | 92.0% | 113 |
| true | true | 8.0% | 113 |

## P(vwap_relationship | displacement)

| displacement = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 32.7% | 1086 |
| false | extended_below | 46.1% | 1086 |
| false | within_band | 21.2% | 1086 |
| true | extended_above | 21.1% | 114 |
| true | extended_below | 48.2% | 114 |
| true | within_band | 30.7% | 114 |

## P(volume_spike | rejection)

| rejection = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 87.2% | 1158 |
| false | true | 12.8% | 1158 |
| true | false | 78.6% | 42 |
| true | true | 21.4% | 42 |

## P(displacement | rejection)

| rejection = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 90.4% | 1158 |
| false | true | 9.6% | 1158 |
| true | false | 92.9% | 42 |
| true | true | 7.1% | 42 |

## P(trend_5m | rejection)

| rejection = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 45.4% | 1072 |
| false | flat | 25.2% | 1072 |
| false | up | 29.4% | 1072 |
| true | down | 57.6% | 33 |
| true | flat | 21.2% | 33 |
| true | up | 21.2% | 33 |

## P(liquidity_sweep | rejection)

| rejection = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 77.1% | 1150 |
| false | true | 22.9% | 1150 |
| true | false | 0.0% | 40 |
| true | true | 100.0% | 40 |

## P(reclaim | rejection)

| rejection = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.9% | 1150 |
| false | true | 2.1% | 1150 |
| true | false | 97.5% | 40 |
| true | true | 2.5% | 40 |

## P(vwap_relationship | rejection)

| rejection = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 31.6% | 1158 |
| false | extended_below | 46.0% | 1158 |
| false | within_band | 22.4% | 1158 |
| true | extended_above | 31.0% | 42 |
| true | extended_below | 54.8% | 42 |
| true | within_band | 14.3% | 42 |

## P(volume_spike | trend_5m)

| trend_5m = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 87.2% | 506 |
| down | true | 12.8% | 506 |
| flat | false | 83.8% | 277 |
| flat | true | 16.2% | 277 |
| up | false | 91.6% | 322 |
| up | true | 8.4% | 322 |

## P(displacement | trend_5m)

| trend_5m = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 89.7% | 506 |
| down | true | 10.3% | 506 |
| flat | false | 88.8% | 277 |
| flat | true | 11.2% | 277 |
| up | false | 95.0% | 322 |
| up | true | 5.0% | 322 |

## P(rejection | trend_5m)

| trend_5m = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 96.2% | 506 |
| down | true | 3.8% | 506 |
| flat | false | 97.5% | 277 |
| flat | true | 2.5% | 277 |
| up | false | 97.8% | 322 |
| up | true | 2.2% | 322 |

## P(liquidity_sweep | trend_5m)

| trend_5m = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 69.6% | 506 |
| down | true | 30.4% | 506 |
| flat | false | 83.0% | 277 |
| flat | true | 17.0% | 277 |
| up | false | 79.8% | 322 |
| up | true | 20.2% | 322 |

## P(reclaim | trend_5m)

| trend_5m = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 97.2% | 506 |
| down | true | 2.8% | 506 |
| flat | false | 98.9% | 277 |
| flat | true | 1.1% | 277 |
| up | false | 98.1% | 322 |
| up | true | 1.9% | 322 |

## P(vwap_relationship | trend_5m)

| trend_5m = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| down | extended_above | 11.3% | 506 |
| down | extended_below | 72.9% | 506 |
| down | within_band | 15.8% | 506 |
| flat | extended_above | 43.3% | 277 |
| flat | extended_below | 30.7% | 277 |
| flat | within_band | 26.0% | 277 |
| up | extended_above | 61.8% | 322 |
| up | extended_below | 20.2% | 322 |
| up | within_band | 18.0% | 322 |

## P(volume_spike | liquidity_sweep)

| liquidity_sweep = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 89.1% | 887 |
| false | true | 10.9% | 887 |
| true | false | 80.2% | 303 |
| true | true | 19.8% | 303 |

## P(displacement | liquidity_sweep)

| liquidity_sweep = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 92.1% | 887 |
| false | true | 7.9% | 887 |
| true | false | 85.8% | 303 |
| true | true | 14.2% | 303 |

## P(rejection | liquidity_sweep)

| liquidity_sweep = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 100.0% | 887 |
| false | true | 0.0% | 887 |
| true | false | 86.8% | 303 |
| true | true | 13.2% | 303 |

## P(trend_5m | liquidity_sweep)

| liquidity_sweep = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 42.0% | 839 |
| false | flat | 27.4% | 839 |
| false | up | 30.6% | 839 |
| true | down | 57.9% | 266 |
| true | flat | 17.7% | 266 |
| true | up | 24.4% | 266 |

## P(reclaim | liquidity_sweep)

| liquidity_sweep = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 100.0% | 887 |
| false | true | 0.0% | 887 |
| true | false | 91.7% | 303 |
| true | true | 8.3% | 303 |

## P(vwap_relationship | liquidity_sweep)

| liquidity_sweep = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 32.0% | 887 |
| false | extended_below | 43.6% | 887 |
| false | within_band | 24.4% | 887 |
| true | extended_above | 31.4% | 303 |
| true | extended_below | 55.4% | 303 |
| true | within_band | 13.2% | 303 |

## P(volume_spike | reclaim)

| reclaim = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 87.2% | 1165 |
| false | true | 12.8% | 1165 |
| true | false | 68.0% | 25 |
| true | true | 32.0% | 25 |

## P(displacement | reclaim)

| reclaim = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 91.1% | 1165 |
| false | true | 8.9% | 1165 |
| true | false | 64.0% | 25 |
| true | true | 36.0% | 25 |

## P(rejection | reclaim)

| reclaim = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 96.7% | 1165 |
| false | true | 3.3% | 1165 |
| true | false | 96.0% | 25 |
| true | true | 4.0% | 25 |

## P(trend_5m | reclaim)

| reclaim = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 45.5% | 1082 |
| false | flat | 25.3% | 1082 |
| false | up | 29.2% | 1082 |
| true | down | 60.9% | 23 |
| true | flat | 13.0% | 23 |
| true | up | 26.1% | 23 |

## P(liquidity_sweep | reclaim)

| reclaim = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 76.1% | 1165 |
| false | true | 23.9% | 1165 |
| true | false | 0.0% | 25 |
| true | true | 100.0% | 25 |

## P(vwap_relationship | reclaim)

| reclaim = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 31.7% | 1165 |
| false | extended_below | 46.5% | 1165 |
| false | within_band | 21.8% | 1165 |
| true | extended_above | 40.0% | 25 |
| true | extended_below | 52.0% | 25 |
| true | within_band | 8.0% | 25 |

## P(volume_spike | vwap_relationship)

| vwap_relationship = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 87.6% | 379 |
| extended_above | true | 12.4% | 379 |
| extended_below | false | 86.5% | 556 |
| extended_below | true | 13.5% | 556 |
| within_band | false | 86.8% | 265 |
| within_band | true | 13.2% | 265 |

## P(displacement | vwap_relationship)

| vwap_relationship = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 93.7% | 379 |
| extended_above | true | 6.3% | 379 |
| extended_below | false | 90.1% | 556 |
| extended_below | true | 9.9% | 556 |
| within_band | false | 86.8% | 265 |
| within_band | true | 13.2% | 265 |

## P(rejection | vwap_relationship)

| vwap_relationship = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 96.6% | 379 |
| extended_above | true | 3.4% | 379 |
| extended_below | false | 95.9% | 556 |
| extended_below | true | 4.1% | 556 |
| within_band | false | 97.7% | 265 |
| within_band | true | 2.3% | 265 |

## P(trend_5m | vwap_relationship)

| vwap_relationship = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | down | 15.2% | 376 |
| extended_above | flat | 31.9% | 376 |
| extended_above | up | 52.9% | 376 |
| extended_below | down | 71.1% | 519 |
| extended_below | flat | 16.4% | 519 |
| extended_below | up | 12.5% | 519 |
| within_band | down | 38.1% | 210 |
| within_band | flat | 34.3% | 210 |
| within_band | up | 27.6% | 210 |

## P(liquidity_sweep | vwap_relationship)

| vwap_relationship = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 74.9% | 379 |
| extended_above | true | 25.1% | 379 |
| extended_below | false | 69.7% | 555 |
| extended_below | true | 30.3% | 555 |
| within_band | false | 84.4% | 256 |
| within_band | true | 15.6% | 256 |

## P(reclaim | vwap_relationship)

| vwap_relationship = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 97.4% | 379 |
| extended_above | true | 2.6% | 379 |
| extended_below | false | 97.7% | 555 |
| extended_below | true | 2.3% | 555 |
| within_band | false | 99.2% | 256 |
| within_band | true | 0.8% | 256 |

# RE-1 Conditional Probability

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T12:55:24.093399+00:00
- **Code version**: a907325fbb357097fb0e8e064d46772e2b719964

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

P(target = target_value | condition = condition_value), over bars where both facts are computable. Exhaustive over every ordered pair of distinct registered facts.

## P(displacement | volume_spike)

| volume_spike = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 96.9% | 83281 |
| false | true | 3.1% | 83281 |
| true | false | 46.4% | 14520 |
| true | true | 53.6% | 14520 |

## P(rejection | volume_spike)

| volume_spike = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.6% | 83281 |
| false | true | 2.4% | 83281 |
| true | false | 94.5% | 14520 |
| true | true | 5.5% | 14520 |

## P(trend_5m | volume_spike)

| volume_spike = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 32.4% | 77004 |
| false | flat | 27.7% | 77004 |
| false | up | 39.9% | 77004 |
| true | down | 37.8% | 14033 |
| true | flat | 27.7% | 14033 |
| true | up | 34.5% | 14033 |

## P(liquidity_sweep | volume_spike)

| volume_spike = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 80.3% | 82608 |
| false | true | 19.7% | 82608 |
| true | false | 63.7% | 14481 |
| true | true | 36.3% | 14481 |

## P(reclaim | volume_spike)

| volume_spike = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.4% | 82608 |
| false | true | 2.6% | 82608 |
| true | false | 94.6% | 14481 |
| true | true | 5.4% | 14481 |

## P(vwap_relationship | volume_spike)

| volume_spike = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 43.9% | 83281 |
| false | extended_below | 29.3% | 83281 |
| false | within_band | 26.8% | 83281 |
| true | extended_above | 43.2% | 14520 |
| true | extended_below | 35.8% | 14520 |
| true | within_band | 21.0% | 14520 |

## P(volume_spike | displacement)

| displacement = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 92.3% | 87451 |
| false | true | 7.7% | 87451 |
| true | false | 24.8% | 10350 |
| true | true | 75.2% | 10350 |

## P(rejection | displacement)

| displacement = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.3% | 87467 |
| false | true | 2.7% | 87467 |
| true | false | 95.9% | 10352 |
| true | true | 4.1% | 10352 |

## P(trend_5m | displacement)

| displacement = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 32.5% | 81177 |
| false | flat | 27.6% | 81177 |
| false | up | 39.9% | 81177 |
| true | down | 39.1% | 9860 |
| true | flat | 28.6% | 9860 |
| true | up | 32.2% | 9860 |

## P(liquidity_sweep | displacement)

| displacement = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 79.3% | 86981 |
| false | true | 20.7% | 86981 |
| true | false | 64.6% | 10126 |
| true | true | 35.4% | 10126 |

## P(reclaim | displacement)

| displacement = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.4% | 86981 |
| false | true | 2.6% | 86981 |
| true | false | 93.4% | 10126 |
| true | true | 6.6% | 10126 |

## P(vwap_relationship | displacement)

| displacement = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 44.3% | 87467 |
| false | extended_below | 29.5% | 87467 |
| false | within_band | 26.2% | 87467 |
| true | extended_above | 39.5% | 10352 |
| true | extended_below | 36.8% | 10352 |
| true | within_band | 23.7% | 10352 |

## P(volume_spike | rejection)

| rejection = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 85.6% | 94995 |
| false | true | 14.4% | 94995 |
| true | false | 71.7% | 2806 |
| true | true | 28.3% | 2806 |

## P(displacement | rejection)

| rejection = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 89.6% | 95012 |
| false | true | 10.4% | 95012 |
| true | false | 84.9% | 2807 |
| true | true | 15.1% | 2807 |

## P(trend_5m | rejection)

| rejection = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 33.1% | 88609 |
| false | flat | 28.0% | 88609 |
| false | up | 38.9% | 88609 |
| true | down | 37.4% | 2428 |
| true | flat | 18.2% | 2428 |
| true | up | 44.4% | 2428 |

## P(liquidity_sweep | rejection)

| rejection = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 80.0% | 94425 |
| false | true | 20.0% | 94425 |
| true | false | 0.0% | 2715 |
| true | true | 100.0% | 2715 |

## P(reclaim | rejection)

| rejection = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.2% | 94425 |
| false | true | 2.8% | 94425 |
| true | false | 88.0% | 2715 |
| true | true | 12.0% | 2715 |

## P(vwap_relationship | rejection)

| rejection = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 43.7% | 95012 |
| false | extended_below | 30.1% | 95012 |
| false | within_band | 26.2% | 95012 |
| true | extended_above | 46.5% | 2807 |
| true | extended_below | 34.9% | 2807 |
| true | within_band | 18.5% | 2807 |

## P(volume_spike | trend_5m)

| trend_5m = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 82.4% | 30241 |
| down | true | 17.6% | 30241 |
| flat | false | 84.6% | 25216 |
| flat | true | 15.4% | 25216 |
| up | false | 86.4% | 35580 |
| up | true | 13.6% | 35580 |

## P(displacement | trend_5m)

| trend_5m = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 87.2% | 30241 |
| down | true | 12.8% | 30241 |
| flat | false | 88.8% | 25216 |
| flat | true | 11.2% | 25216 |
| up | false | 91.1% | 35580 |
| up | true | 8.9% | 35580 |

## P(rejection | trend_5m)

| trend_5m = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 97.0% | 30241 |
| down | true | 3.0% | 30241 |
| flat | false | 98.2% | 25216 |
| flat | true | 1.8% | 25216 |
| up | false | 97.0% | 35580 |
| up | true | 3.0% | 35580 |

## P(liquidity_sweep | trend_5m)

| trend_5m = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 76.3% | 30241 |
| down | true | 23.7% | 30241 |
| flat | false | 85.9% | 25216 |
| flat | true | 14.1% | 25216 |
| up | false | 76.1% | 35580 |
| up | true | 23.9% | 35580 |

## P(reclaim | trend_5m)

| trend_5m = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 96.3% | 30241 |
| down | true | 3.7% | 30241 |
| flat | false | 97.0% | 25216 |
| flat | true | 3.0% | 25216 |
| up | false | 97.1% | 35580 |
| up | true | 2.9% | 35580 |

## P(vwap_relationship | trend_5m)

| trend_5m = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| down | extended_above | 17.0% | 30241 |
| down | extended_below | 61.0% | 30241 |
| down | within_band | 22.0% | 30241 |
| flat | extended_above | 43.8% | 25216 |
| flat | extended_below | 27.6% | 25216 |
| flat | within_band | 28.6% | 25216 |
| up | extended_above | 72.3% | 35580 |
| up | extended_below | 9.8% | 35580 |
| up | within_band | 17.9% | 35580 |

## P(volume_spike | liquidity_sweep)

| liquidity_sweep = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 87.8% | 75515 |
| false | true | 12.2% | 75515 |
| true | false | 75.6% | 21574 |
| true | true | 24.4% | 21574 |

## P(displacement | liquidity_sweep)

| liquidity_sweep = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 91.3% | 75528 |
| false | true | 8.7% | 75528 |
| true | false | 83.4% | 21579 |
| true | true | 16.6% | 21579 |

## P(rejection | liquidity_sweep)

| liquidity_sweep = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 100.0% | 75545 |
| false | true | 0.0% | 75545 |
| true | false | 87.4% | 21595 |
| true | true | 12.6% | 21595 |

## P(trend_5m | liquidity_sweep)

| liquidity_sweep = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 32.1% | 71831 |
| false | flat | 30.2% | 71831 |
| false | up | 37.7% | 71831 |
| true | down | 37.3% | 19206 |
| true | flat | 18.5% | 19206 |
| true | up | 44.2% | 19206 |

## P(reclaim | liquidity_sweep)

| liquidity_sweep = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 100.0% | 75545 |
| false | true | 0.0% | 75545 |
| true | false | 86.3% | 21595 |
| true | true | 13.7% | 21595 |

## P(vwap_relationship | liquidity_sweep)

| liquidity_sweep = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 43.2% | 75528 |
| false | extended_below | 29.1% | 75528 |
| false | within_band | 27.6% | 75528 |
| true | extended_above | 47.2% | 21579 |
| true | extended_below | 35.1% | 21579 |
| true | within_band | 17.7% | 21579 |

## P(volume_spike | reclaim)

| reclaim = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 85.4% | 94123 |
| false | true | 14.6% | 94123 |
| true | false | 73.7% | 2966 |
| true | true | 26.3% | 2966 |

## P(displacement | reclaim)

| reclaim = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 89.9% | 94141 |
| false | true | 10.1% | 94141 |
| true | false | 77.6% | 2966 |
| true | true | 22.4% | 2966 |

## P(rejection | reclaim)

| reclaim = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.5% | 94174 |
| false | true | 2.5% | 94174 |
| true | false | 89.0% | 2966 |
| true | true | 11.0% | 2966 |

## P(trend_5m | reclaim)

| reclaim = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 33.0% | 88147 |
| false | flat | 27.7% | 88147 |
| false | up | 39.2% | 88147 |
| true | down | 38.4% | 2890 |
| true | flat | 26.4% | 2890 |
| true | up | 35.2% | 2890 |

## P(liquidity_sweep | reclaim)

| reclaim = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 80.2% | 94174 |
| false | true | 19.8% | 94174 |
| true | false | 0.0% | 2966 |
| true | true | 100.0% | 2966 |

## P(vwap_relationship | reclaim)

| reclaim = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 44.3% | 94141 |
| false | extended_below | 30.3% | 94141 |
| false | within_band | 25.4% | 94141 |
| true | extended_above | 38.6% | 2966 |
| true | extended_below | 34.9% | 2966 |
| true | within_band | 26.5% | 2966 |

## P(volume_spike | vwap_relationship)

| vwap_relationship = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 85.4% | 42867 |
| extended_above | true | 14.6% | 42867 |
| extended_below | false | 82.4% | 29579 |
| extended_below | true | 17.6% | 29579 |
| within_band | false | 88.0% | 25355 |
| within_band | true | 12.0% | 25355 |

## P(displacement | vwap_relationship)

| vwap_relationship = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 90.5% | 42867 |
| extended_above | true | 9.5% | 42867 |
| extended_below | false | 87.1% | 29585 |
| extended_below | true | 12.9% | 29585 |
| within_band | false | 90.3% | 25367 |
| within_band | true | 9.7% | 25367 |

## P(rejection | vwap_relationship)

| vwap_relationship = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 97.0% | 42867 |
| extended_above | true | 3.0% | 42867 |
| extended_below | false | 96.7% | 29585 |
| extended_below | true | 3.3% | 29585 |
| within_band | false | 98.0% | 25367 |
| within_band | true | 2.0% | 25367 |

## P(trend_5m | vwap_relationship)

| vwap_relationship = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | down | 12.3% | 41921 |
| extended_above | flat | 26.3% | 41921 |
| extended_above | up | 61.4% | 41921 |
| extended_below | down | 63.9% | 28896 |
| extended_below | flat | 24.0% | 28896 |
| extended_below | up | 12.1% | 28896 |
| within_band | down | 32.8% | 20220 |
| within_band | flat | 35.7% | 20220 |
| within_band | up | 31.4% | 20220 |

## P(liquidity_sweep | vwap_relationship)

| vwap_relationship = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 76.2% | 42840 |
| extended_above | true | 23.8% | 42840 |
| extended_below | false | 74.4% | 29571 |
| extended_below | true | 25.6% | 29571 |
| within_band | false | 84.5% | 24696 |
| within_band | true | 15.5% | 24696 |

## P(reclaim | vwap_relationship)

| vwap_relationship = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 97.3% | 42840 |
| extended_above | true | 2.7% | 42840 |
| extended_below | false | 96.5% | 29571 |
| extended_below | true | 3.5% | 29571 |
| within_band | false | 96.8% | 24696 |
| within_band | true | 3.2% | 24696 |

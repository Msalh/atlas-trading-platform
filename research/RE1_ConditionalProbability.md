# RE-1 Conditional Probability

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-09-30T15:10:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 56490
- **Generated at**: 2026-07-20T12:03:27.987976+00:00
- **Code version**: faacf83cf2ac43c8ac4182629d75a5540bc7215f

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

P(target = target_value | condition = condition_value), over bars where both facts are computable. Exhaustive over every ordered pair of distinct registered facts.

## P(displacement | volume_spike)

| volume_spike = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 96.8% | 48389 |
| false | true | 3.2% | 48389 |
| true | false | 46.4% | 8082 |
| true | true | 53.6% | 8082 |

## P(rejection | volume_spike)

| volume_spike = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.4% | 48389 |
| false | true | 2.6% | 48389 |
| true | false | 94.6% | 8082 |
| true | true | 5.4% | 8082 |

## P(trend_5m | volume_spike)

| volume_spike = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 32.4% | 44772 |
| false | flat | 27.0% | 44772 |
| false | up | 40.5% | 44772 |
| true | down | 38.4% | 7747 |
| true | flat | 27.4% | 7747 |
| true | up | 34.2% | 7747 |

## P(liquidity_sweep | volume_spike)

| volume_spike = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 79.3% | 47998 |
| false | true | 20.7% | 47998 |
| true | false | 62.8% | 8057 |
| true | true | 37.2% | 8057 |

## P(reclaim | volume_spike)

| volume_spike = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.4% | 47998 |
| false | true | 2.6% | 47998 |
| true | false | 94.7% | 8057 |
| true | true | 5.3% | 8057 |

## P(vwap_relationship | volume_spike)

| volume_spike = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 44.2% | 48389 |
| false | extended_below | 30.0% | 48389 |
| false | within_band | 25.7% | 48389 |
| true | extended_above | 43.2% | 8082 |
| true | extended_below | 36.2% | 8082 |
| true | within_band | 20.6% | 8082 |

## P(volume_spike | displacement)

| displacement = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 92.6% | 50596 |
| false | true | 7.4% | 50596 |
| true | false | 26.2% | 5875 |
| true | true | 73.8% | 5875 |

## P(rejection | displacement)

| displacement = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.1% | 50602 |
| false | true | 2.9% | 50602 |
| true | false | 95.6% | 5875 |
| true | true | 4.4% | 5875 |

## P(trend_5m | displacement)

| displacement = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 32.6% | 46972 |
| false | flat | 26.9% | 46972 |
| false | up | 40.5% | 46972 |
| true | down | 39.2% | 5547 |
| true | flat | 28.4% | 5547 |
| true | up | 32.4% | 5547 |

## P(liquidity_sweep | displacement)

| displacement = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 78.4% | 50324 |
| false | true | 21.6% | 50324 |
| true | false | 64.3% | 5737 |
| true | true | 35.7% | 5737 |

## P(reclaim | displacement)

| displacement = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.4% | 50324 |
| false | true | 2.6% | 50324 |
| true | false | 93.7% | 5737 |
| true | true | 6.3% | 5737 |

## P(vwap_relationship | displacement)

| displacement = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 44.5% | 50602 |
| false | extended_below | 30.3% | 50602 |
| false | within_band | 25.2% | 50602 |
| true | extended_above | 40.3% | 5875 |
| true | extended_below | 36.4% | 5875 |
| true | within_band | 23.3% | 5875 |

## P(volume_spike | rejection)

| rejection = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 86.0% | 54770 |
| false | true | 14.0% | 54770 |
| true | false | 74.3% | 1701 |
| true | true | 25.7% | 1701 |

## P(displacement | rejection)

| rejection = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 89.7% | 54776 |
| false | true | 10.3% | 54776 |
| true | false | 84.8% | 1701 |
| true | true | 15.2% | 1701 |

## P(trend_5m | rejection)

| rejection = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 33.2% | 51049 |
| false | flat | 27.4% | 51049 |
| false | up | 39.5% | 51049 |
| true | down | 38.0% | 1470 |
| true | flat | 18.0% | 1470 |
| true | up | 44.0% | 1470 |

## P(liquidity_sweep | rejection)

| rejection = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 79.3% | 54439 |
| false | true | 20.7% | 54439 |
| true | false | 0.0% | 1633 |
| true | true | 100.0% | 1633 |

## P(reclaim | rejection)

| rejection = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.3% | 54439 |
| false | true | 2.7% | 54439 |
| true | false | 88.9% | 1633 |
| true | true | 11.1% | 1633 |

## P(vwap_relationship | rejection)

| rejection = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 44.0% | 54776 |
| false | extended_below | 30.8% | 54776 |
| false | within_band | 25.2% | 54776 |
| true | extended_above | 46.7% | 1701 |
| true | extended_below | 34.9% | 1701 |
| true | within_band | 18.4% | 1701 |

## P(volume_spike | trend_5m)

| trend_5m = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 83.0% | 17488 |
| down | true | 17.0% | 17488 |
| flat | false | 85.1% | 14227 |
| flat | true | 14.9% | 14227 |
| up | false | 87.3% | 20804 |
| up | true | 12.7% | 20804 |

## P(displacement | trend_5m)

| trend_5m = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 87.6% | 17488 |
| down | true | 12.4% | 17488 |
| flat | false | 88.9% | 14227 |
| flat | true | 11.1% | 14227 |
| up | false | 91.4% | 20804 |
| up | true | 8.6% | 20804 |

## P(rejection | trend_5m)

| trend_5m = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 96.8% | 17488 |
| down | true | 3.2% | 17488 |
| flat | false | 98.1% | 14227 |
| flat | true | 1.9% | 14227 |
| up | false | 96.9% | 20804 |
| up | true | 3.1% | 20804 |

## P(liquidity_sweep | trend_5m)

| trend_5m = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 75.5% | 17488 |
| down | true | 24.5% | 17488 |
| flat | false | 85.6% | 14227 |
| flat | true | 14.4% | 14227 |
| up | false | 75.2% | 20804 |
| up | true | 24.8% | 20804 |

## P(reclaim | trend_5m)

| trend_5m = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| down | false | 96.4% | 17488 |
| down | true | 3.6% | 17488 |
| flat | false | 97.0% | 14227 |
| flat | true | 3.0% | 14227 |
| up | false | 97.3% | 20804 |
| up | true | 2.7% | 20804 |

## P(vwap_relationship | trend_5m)

| trend_5m = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| down | extended_above | 17.1% | 17488 |
| down | extended_below | 62.4% | 17488 |
| down | within_band | 20.5% | 17488 |
| flat | extended_above | 44.4% | 14227 |
| flat | extended_below | 27.7% | 14227 |
| flat | within_band | 27.8% | 14227 |
| up | extended_above | 72.2% | 20804 |
| up | extended_below | 10.3% | 20804 |
| up | within_band | 17.5% | 20804 |

## P(volume_spike | liquidity_sweep)

| liquidity_sweep = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 88.3% | 43129 |
| false | true | 11.7% | 43129 |
| true | false | 76.8% | 12926 |
| true | true | 23.2% | 12926 |

## P(displacement | liquidity_sweep)

| liquidity_sweep = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 91.4% | 43135 |
| false | true | 8.6% | 43135 |
| true | false | 84.2% | 12926 |
| true | true | 15.8% | 12926 |

## P(rejection | liquidity_sweep)

| liquidity_sweep = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 100.0% | 43143 |
| false | true | 0.0% | 43143 |
| true | false | 87.4% | 12929 |
| true | true | 12.6% | 12929 |

## P(trend_5m | liquidity_sweep)

| liquidity_sweep = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 32.2% | 41029 |
| false | flat | 29.7% | 41029 |
| false | up | 38.1% | 41029 |
| true | down | 37.3% | 11490 |
| true | flat | 17.8% | 11490 |
| true | up | 44.9% | 11490 |

## P(reclaim | liquidity_sweep)

| liquidity_sweep = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 100.0% | 43143 |
| false | true | 0.0% | 43143 |
| true | false | 87.1% | 12929 |
| true | true | 12.9% | 12929 |

## P(vwap_relationship | liquidity_sweep)

| liquidity_sweep = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 43.2% | 43135 |
| false | extended_below | 30.0% | 43135 |
| false | within_band | 26.8% | 43135 |
| true | extended_above | 48.3% | 12926 |
| true | extended_below | 34.9% | 12926 |
| true | within_band | 16.9% | 12926 |

## P(volume_spike | reclaim)

| reclaim = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 86.0% | 54390 |
| false | true | 14.0% | 54390 |
| true | false | 74.5% | 1665 |
| true | true | 25.5% | 1665 |

## P(displacement | reclaim)

| reclaim = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 90.1% | 54396 |
| false | true | 9.9% | 54396 |
| true | false | 78.4% | 1665 |
| true | true | 21.6% | 1665 |

## P(rejection | reclaim)

| reclaim = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 97.3% | 54407 |
| false | true | 2.7% | 54407 |
| true | false | 89.1% | 1665 |
| true | true | 10.9% | 1665 |

## P(trend_5m | reclaim)

| reclaim = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| false | down | 33.1% | 50894 |
| false | flat | 27.1% | 50894 |
| false | up | 39.8% | 50894 |
| true | down | 39.1% | 1625 |
| true | flat | 26.0% | 1625 |
| true | up | 34.8% | 1625 |

## P(liquidity_sweep | reclaim)

| reclaim = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| false | false | 79.3% | 54407 |
| false | true | 20.7% | 54407 |
| true | false | 0.0% | 1665 |
| true | true | 100.0% | 1665 |

## P(vwap_relationship | reclaim)

| reclaim = | vwap_relationship = | probability | n (condition sample size) |
|---|---|---|---|
| false | extended_above | 44.5% | 54396 |
| false | extended_below | 31.0% | 54396 |
| false | within_band | 24.5% | 54396 |
| true | extended_above | 39.0% | 1665 |
| true | extended_below | 35.4% | 1665 |
| true | within_band | 25.6% | 1665 |

## P(volume_spike | vwap_relationship)

| vwap_relationship = | volume_spike = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 86.0% | 24892 |
| extended_above | true | 14.0% | 24892 |
| extended_below | false | 83.3% | 17465 |
| extended_below | true | 16.7% | 17465 |
| within_band | false | 88.2% | 14114 |
| within_band | true | 11.8% | 14114 |

## P(displacement | vwap_relationship)

| vwap_relationship = | displacement = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 90.5% | 24892 |
| extended_above | true | 9.5% | 24892 |
| extended_below | false | 87.8% | 17465 |
| extended_below | true | 12.2% | 17465 |
| within_band | false | 90.3% | 14120 |
| within_band | true | 9.7% | 14120 |

## P(rejection | vwap_relationship)

| vwap_relationship = | rejection = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 96.8% | 24892 |
| extended_above | true | 3.2% | 24892 |
| extended_below | false | 96.6% | 17465 |
| extended_below | true | 3.4% | 17465 |
| within_band | false | 97.8% | 14120 |
| within_band | true | 2.2% | 14120 |

## P(trend_5m | vwap_relationship)

| vwap_relationship = | trend_5m = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | down | 12.3% | 24332 |
| extended_above | flat | 26.0% | 24332 |
| extended_above | up | 61.7% | 24332 |
| extended_below | down | 64.2% | 16989 |
| extended_below | flat | 23.2% | 16989 |
| extended_below | up | 12.6% | 16989 |
| within_band | down | 32.1% | 11198 |
| within_band | flat | 35.4% | 11198 |
| within_band | up | 32.6% | 11198 |

## P(liquidity_sweep | vwap_relationship)

| vwap_relationship = | liquidity_sweep = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 74.9% | 24879 |
| extended_above | true | 25.1% | 24879 |
| extended_below | false | 74.2% | 17454 |
| extended_below | true | 25.8% | 17454 |
| within_band | false | 84.1% | 13728 |
| within_band | true | 15.9% | 13728 |

## P(reclaim | vwap_relationship)

| vwap_relationship = | reclaim = | probability | n (condition sample size) |
|---|---|---|---|
| extended_above | false | 97.4% | 24879 |
| extended_above | true | 2.6% | 24879 |
| extended_below | false | 96.6% | 17454 |
| extended_below | true | 3.4% | 17454 |
| within_band | false | 96.9% | 13728 |
| within_band | true | 3.1% | 13728 |

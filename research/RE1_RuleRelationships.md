# RE-1 Rule Relationships

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-09-30T15:10:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 56490
- **Generated at**: 2026-07-20T12:03:27.987976+00:00
- **Code version**: faacf83cf2ac43c8ac4182629d75a5540bc7215f

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## Boolean fact pairs

| fact A | fact B | n | P(A) | P(B) | P(A and B) | lift | correlation | P(A\|B) - P(A) |
|---|---|---|---|---|---|---|---|---|
| volume_spike | displacement | 56471 | 14.3% | 10.4% | 7.7% | 5.153 | 0.578 | 0.594 |
| volume_spike | rejection | 56471 | 14.3% | 3.0% | 0.8% | 1.795 | 0.057 | 0.114 |
| volume_spike | liquidity_sweep | 56055 | 14.4% | 23.1% | 5.3% | 1.612 | 0.137 | 0.088 |
| volume_spike | reclaim | 56055 | 14.4% | 3.0% | 0.8% | 1.772 | 0.055 | 0.111 |
| displacement | rejection | 56477 | 10.4% | 3.0% | 0.5% | 1.458 | 0.028 | 0.048 |
| displacement | liquidity_sweep | 56061 | 10.2% | 23.1% | 3.7% | 1.548 | 0.101 | 0.056 |
| displacement | reclaim | 56061 | 10.2% | 3.0% | 0.6% | 2.113 | 0.066 | 0.114 |
| rejection | liquidity_sweep | 56072 | 2.9% | 23.1% | 2.9% | 4.337 | 0.316 | 0.097 |
| rejection | reclaim | 56072 | 2.9% | 3.0% | 0.3% | 3.733 | 0.083 | 0.080 |
| liquidity_sweep | reclaim | 56072 | 23.1% | 3.0% | 3.0% | 4.337 | 0.320 | 0.769 |

lift > 1 means the two facts co-occur more often than independence would predict; lift < 1 means less often. correlation is the Pearson coefficient over the two facts' 0/1 series. Neither implies causation or a trading edge - purely descriptive association.

## Pairs involving an enum fact (trend_5m, vwap_relationship)

No single lift/correlation number applies (no single 'positive' value) - reported as a joint frequency (contingency) table instead.

### volume_spike x trend_5m (n=52519)

| volume_spike \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 14514 | 12106 | 18152 |
| true | 2974 | 2121 | 2652 |

### volume_spike x vwap_relationship (n=56471)

| volume_spike \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 21401 | 14540 | 12448 |
| true | 3491 | 2925 | 1666 |

### displacement x trend_5m (n=52519)

| displacement \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 15312 | 12651 | 19009 |
| true | 2176 | 1576 | 1795 |

### displacement x vwap_relationship (n=56477)

| displacement \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 22522 | 15326 | 12754 |
| true | 2370 | 2139 | 1366 |

### rejection x trend_5m (n=52519)

| rejection \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 16929 | 13963 | 20157 |
| true | 559 | 264 | 647 |

### rejection x vwap_relationship (n=56477)

| rejection \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 24098 | 16871 | 13807 |
| true | 794 | 594 | 313 |

### trend_5m x liquidity_sweep (n=52519)

| trend_5m \ liquidity_sweep | false | true |
|---|---|---|
| down | 13204 | 4284 |
| flat | 12183 | 2044 |
| up | 15642 | 5162 |

### trend_5m x reclaim (n=52519)

| trend_5m \ reclaim | false | true |
|---|---|---|
| down | 16852 | 636 |
| flat | 13804 | 423 |
| up | 20238 | 566 |

### trend_5m x vwap_relationship (n=52519)

| trend_5m \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| down | 2992 | 10907 | 3589 |
| flat | 6320 | 3947 | 3960 |
| up | 15020 | 2135 | 3649 |

### liquidity_sweep x vwap_relationship (n=56061)

| liquidity_sweep \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 18638 | 12948 | 11549 |
| true | 6241 | 4506 | 2179 |

### reclaim x vwap_relationship (n=56061)

| reclaim \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 24230 | 16865 | 13301 |
| true | 649 | 589 | 427 |

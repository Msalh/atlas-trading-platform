# RE-1 Rule Relationships

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T12:55:24.093399+00:00
- **Code version**: a907325fbb357097fb0e8e064d46772e2b719964

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## Boolean fact pairs

| fact A | fact B | n | P(A) | P(B) | P(A and B) | lift | correlation | P(A\|B) - P(A) |
|---|---|---|---|---|---|---|---|---|
| volume_spike | displacement | 97801 | 14.8% | 10.6% | 8.0% | 5.067 | 0.584 | 0.604 |
| volume_spike | rejection | 97801 | 14.8% | 2.9% | 0.8% | 1.906 | 0.065 | 0.135 |
| volume_spike | liquidity_sweep | 97089 | 14.9% | 22.2% | 5.4% | 1.636 | 0.142 | 0.095 |
| volume_spike | reclaim | 97089 | 14.9% | 3.1% | 0.8% | 1.761 | 0.057 | 0.113 |
| displacement | rejection | 97819 | 10.6% | 2.9% | 0.4% | 1.427 | 0.025 | 0.045 |
| displacement | liquidity_sweep | 97107 | 10.4% | 22.2% | 3.7% | 1.591 | 0.108 | 0.062 |
| displacement | reclaim | 97107 | 10.4% | 3.1% | 0.7% | 2.147 | 0.069 | 0.120 |
| rejection | liquidity_sweep | 97140 | 2.8% | 22.2% | 2.8% | 4.498 | 0.317 | 0.098 |
| rejection | reclaim | 97140 | 2.8% | 3.1% | 0.3% | 3.920 | 0.088 | 0.082 |
| liquidity_sweep | reclaim | 97140 | 22.2% | 3.1% | 3.1% | 4.498 | 0.332 | 0.778 |

lift > 1 means the two facts co-occur more often than independence would predict; lift < 1 means less often. correlation is the Pearson coefficient over the two facts' 0/1 series. Neither implies causation or a trading edge - purely descriptive association.

## Pairs involving an enum fact (trend_5m, vwap_relationship)

No single lift/correlation number applies (no single 'positive' value) - reported as a joint frequency (contingency) table instead.

### volume_spike x trend_5m (n=91037)

| volume_spike \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 24931 | 21332 | 30741 |
| true | 5310 | 3884 | 4839 |

### volume_spike x vwap_relationship (n=97801)

| volume_spike \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 36596 | 24383 | 22302 |
| true | 6271 | 5196 | 3053 |

### displacement x trend_5m (n=91037)

| displacement \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 26383 | 22392 | 32402 |
| true | 3858 | 2824 | 3178 |

### displacement x vwap_relationship (n=97819)

| displacement \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 38778 | 25777 | 22912 |
| true | 4089 | 3808 | 2455 |

### rejection x trend_5m (n=91037)

| rejection \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 29334 | 24774 | 34501 |
| true | 907 | 442 | 1079 |

### rejection x vwap_relationship (n=97819)

| rejection \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 41561 | 28604 | 24847 |
| true | 1306 | 981 | 520 |

### trend_5m x liquidity_sweep (n=91037)

| trend_5m \ liquidity_sweep | false | true |
|---|---|---|
| down | 23076 | 7165 |
| flat | 21663 | 3553 |
| up | 27092 | 8488 |

### trend_5m x reclaim (n=91037)

| trend_5m \ reclaim | false | true |
|---|---|---|
| down | 29131 | 1110 |
| flat | 24452 | 764 |
| up | 34564 | 1016 |

### trend_5m x vwap_relationship (n=91037)

| trend_5m \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| down | 5142 | 18458 | 6641 |
| flat | 11046 | 6948 | 7222 |
| up | 25733 | 3490 | 6357 |

### liquidity_sweep x vwap_relationship (n=97107)

| liquidity_sweep \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 32660 | 21998 | 20870 |
| true | 10180 | 7573 | 3826 |

### reclaim x vwap_relationship (n=97107)

| reclaim \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 41695 | 28536 | 23910 |
| true | 1145 | 1035 | 786 |

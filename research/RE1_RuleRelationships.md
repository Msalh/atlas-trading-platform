# RE-1 Rule Relationships

> **VALIDATION RUN** - this report exists to prove the RE-1 pipeline computes correctly, not to characterize real market behavior. The dataset behind it (1200 bars) is a correctness-validation dataset, not a basis for any market-characteristics or trading conclusion. The same pipeline, unchanged, is designed to be re-run against a much larger historical dataset once one is available.

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2026-07-13T13:05:00+00:00 -> 2026-07-17T21:00:00+00:00
- **Source**: csv:../data/CME_MINI_MNQ.csv
- **Row count**: 1200
- **Generated at**: 2026-07-20T11:44:35.275973+00:00
- **Code version**: 1a97a859c72e2fbd1eed01bf891bf5c35ddd5f6c

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## Boolean fact pairs

| fact A | fact B | n | P(A) | P(B) | P(A and B) | lift | correlation | P(A\|B) - P(A) |
|---|---|---|---|---|---|---|---|---|
| volume_spike | displacement | 1200 | 13.1% | 9.5% | 6.6% | 5.297 | 0.540 | 0.562 |
| volume_spike | rejection | 1200 | 13.1% | 3.5% | 0.8% | 1.638 | 0.047 | 0.083 |
| volume_spike | liquidity_sweep | 1190 | 13.2% | 25.5% | 5.0% | 1.501 | 0.114 | 0.066 |
| volume_spike | reclaim | 1190 | 13.2% | 2.1% | 0.7% | 2.425 | 0.081 | 0.188 |
| displacement | rejection | 1200 | 9.5% | 3.5% | 0.2% | 0.752 | -0.015 | -0.024 |
| displacement | liquidity_sweep | 1190 | 9.5% | 25.5% | 3.6% | 1.494 | 0.094 | 0.047 |
| displacement | reclaim | 1190 | 9.5% | 2.1% | 0.8% | 3.791 | 0.132 | 0.265 |
| rejection | liquidity_sweep | 1190 | 3.4% | 25.5% | 3.4% | 3.927 | 0.319 | 0.098 |
| rejection | reclaim | 1190 | 3.4% | 2.1% | 0.1% | 1.190 | 0.005 | 0.006 |
| liquidity_sweep | reclaim | 1190 | 25.5% | 2.1% | 2.1% | 3.927 | 0.251 | 0.745 |

lift > 1 means the two facts co-occur more often than independence would predict; lift < 1 means less often. correlation is the Pearson coefficient over the two facts' 0/1 series. Neither implies causation or a trading edge - purely descriptive association.

## Pairs involving an enum fact (trend_5m, vwap_relationship)

No single lift/correlation number applies (no single 'positive' value) - reported as a joint frequency (contingency) table instead.

### volume_spike x trend_5m (n=1105)

| volume_spike \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 441 | 232 | 295 |
| true | 65 | 45 | 27 |

### volume_spike x vwap_relationship (n=1200)

| volume_spike \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 332 | 481 | 230 |
| true | 47 | 75 | 35 |

### displacement x trend_5m (n=1105)

| displacement \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 454 | 246 | 306 |
| true | 52 | 31 | 16 |

### displacement x vwap_relationship (n=1200)

| displacement \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 355 | 501 | 230 |
| true | 24 | 55 | 35 |

### rejection x trend_5m (n=1105)

| rejection \ trend_5m | down | flat | up |
|---|---|---|---|
| false | 487 | 270 | 315 |
| true | 19 | 7 | 7 |

### rejection x vwap_relationship (n=1200)

| rejection \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 366 | 533 | 259 |
| true | 13 | 23 | 6 |

### trend_5m x liquidity_sweep (n=1105)

| trend_5m \ liquidity_sweep | false | true |
|---|---|---|
| down | 352 | 154 |
| flat | 230 | 47 |
| up | 257 | 65 |

### trend_5m x reclaim (n=1105)

| trend_5m \ reclaim | false | true |
|---|---|---|
| down | 492 | 14 |
| flat | 274 | 3 |
| up | 316 | 6 |

### trend_5m x vwap_relationship (n=1105)

| trend_5m \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| down | 57 | 369 | 80 |
| flat | 120 | 85 | 72 |
| up | 199 | 65 | 58 |

### liquidity_sweep x vwap_relationship (n=1190)

| liquidity_sweep \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 284 | 387 | 216 |
| true | 95 | 168 | 40 |

### reclaim x vwap_relationship (n=1190)

| reclaim \ vwap_relationship | extended_above | extended_below | within_band |
|---|---|---|---|
| false | 369 | 542 | 254 |
| true | 10 | 13 | 2 |

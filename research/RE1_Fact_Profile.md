# RE-1 Fact Profile

> **VALIDATION RUN** - this report exists to prove the RE-1 pipeline computes correctly, not to characterize real market behavior. The dataset behind it (1200 bars) is a correctness-validation dataset, not a basis for any market-characteristics or trading conclusion. The same pipeline, unchanged, is designed to be re-run against a much larger historical dataset once one is available.

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2026-07-13T13:05:00+00:00 -> 2026-07-17T21:00:00+00:00
- **Source**: csv:../data/CME_MINI_MNQ.csv
- **Row count**: 1200
- **Generated at**: 2026-07-20T11:44:35.275973+00:00
- **Code version**: 1a97a859c72e2fbd1eed01bf891bf5c35ddd5f6c

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## volume_spike (boolean)

- Computable: 1200  Insufficient data: 0
- True: 13.1% (157)  False: 1043

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 71 | 14.69 | 8 | 55 | 68 |
| true | 66 | 2.38 | 1 | 8 | 11 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 93.6% | 6.4% |
| true | 42.0% | 58.0% |

## displacement (boolean)

- Computable: 1200  Insufficient data: 0
- True: 9.5% (114)  False: 1086

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 76 | 14.29 | 8 | 64 | 77 |
| true | 72 | 1.58 | 1 | 7 | 8 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 93.4% | 6.6% |
| true | 63.2% | 36.8% |

## rejection (boolean)

- Computable: 1200  Insufficient data: 0
- True: 3.5% (42)  False: 1158

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 43 | 26.93 | 13 | 149 | 178 |
| true | 40 | 1.05 | 1 | 1 | 3 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 96.6% | 3.4% |
| true | 95.1% | 4.9% |

## trend_5m (enum)

- Computable: 1105  Insufficient data: 95
- First-order distribution (value: count):
  - down: 506 (45.8%)
  - flat: 277 (25.1%)
  - up: 322 (29.1%)

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| down | 29 | 17.45 | 17 | 41 | 44 |
| flat | 53 | 5.23 | 3 | 14 | 45 |
| up | 26 | 12.38 | 11 | 22 | 30 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | down | flat | up |
|---|---|---|---|
| down | 94.5% | 5.5% | 0.0% |
| flat | 9.5% | 81.5% | 9.1% |
| up | 0.0% | 7.5% | 92.5% |

## liquidity_sweep (boolean)

- Computable: 1190  Insufficient data: 10
- True: 25.5% (303)  False: 887

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 56 | 15.84 | 8 | 59 | 151 |
| true | 55 | 5.51 | 4 | 12 | 21 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 94.1% | 5.9% |
| true | 17.9% | 82.1% |

## reclaim (boolean)

- Computable: 1190  Insufficient data: 10
- True: 2.1% (25)  False: 1165

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 21 | 55.48 | 28 | 188 | 189 |
| true | 16 | 1.56 | 1 | 3 | 3 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 98.6% | 1.4% |
| true | 64.0% | 36.0% |

## vwap_relationship (enum)

- Computable: 1200  Insufficient data: 0
- First-order distribution (value: count):
  - extended_above: 379 (31.6%)
  - extended_below: 556 (46.3%)
  - within_band: 265 (22.1%)

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| extended_above | 25 | 15.16 | 3 | 75 | 115 |
| extended_below | 40 | 13.90 | 2 | 64 | 126 |
| within_band | 66 | 4.02 | 3 | 12 | 16 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | extended_above | extended_below | within_band |
|---|---|---|---|
| extended_above | 93.7% | 0.0% | 6.3% |
| extended_below | 0.0% | 93.3% | 6.7% |
| within_band | 9.5% | 15.2% | 75.4% |

# RE-1 Fact Profile

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T12:55:24.093399+00:00
- **Code version**: a907325fbb357097fb0e8e064d46772e2b719964

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## volume_spike (boolean)

- Computable: 97801  Insufficient data: 57
- True: 14.8% (14520)  False: 83281

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 7607 | 10.95 | 6 | 38 | 89 |
| true | 7284 | 1.99 | 1 | 6 | 17 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 91.3% | 8.7% |
| true | 50.2% | 49.8% |

## displacement (boolean)

- Computable: 97819  Insufficient data: 39
- True: 10.6% (10352)  False: 87467

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 7500 | 11.66 | 7 | 38 | 95 |
| true | 7331 | 1.41 | 1 | 3 | 10 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 91.8% | 8.2% |
| true | 70.8% | 29.2% |

## rejection (boolean)

- Computable: 97858  Insufficient data: 0
- True: 2.9% (2810)  False: 95048

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 2842 | 33.44 | 14 | 131 | 273 |
| true | 2564 | 1.10 | 1 | 2 | 4 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 97.4% | 2.6% |
| true | 91.2% | 8.8% |

## trend_5m (enum)

- Computable: 91037  Insufficient data: 6821
- First-order distribution (value: count):
  - down: 30241 (33.2%)
  - flat: 25216 (27.7%)
  - up: 35580 (39.1%)

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| down | 2156 | 14.03 | 12 | 34 | 116 |
| flat | 4413 | 5.71 | 4 | 15 | 47 |
| up | 2404 | 14.80 | 13 | 37 | 96 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | down | flat | up |
|---|---|---|---|
| down | 93.3% | 6.7% | 0.0% |
| flat | 8.2% | 82.8% | 9.0% |
| up | 0.0% | 6.4% | 93.6% |

## liquidity_sweep (boolean)

- Computable: 97140  Insufficient data: 718
- True: 22.2% (21595)  False: 75545

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 4758 | 15.88 | 6 | 68 | 262 |
| true | 4819 | 4.48 | 4 | 11 | 31 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 94.0% | 6.0% |
| true | 21.9% | 78.1% |

## reclaim (boolean)

- Computable: 97140  Insufficient data: 718
- True: 3.1% (2966)  False: 94174

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 2122 | 44.38 | 11 | 199 | 274 |
| true | 1779 | 1.67 | 2 | 2 | 5 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 98.1% | 1.9% |
| true | 59.9% | 40.1% |

## vwap_relationship (enum)

- Computable: 97819  Insufficient data: 39
- First-order distribution (value: count):
  - extended_above: 42867 (43.8%)
  - extended_below: 29585 (30.2%)
  - within_band: 25367 (25.9%)

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| extended_above | 2727 | 15.72 | 3 | 78 | 256 |
| extended_below | 2695 | 10.98 | 3 | 55 | 224 |
| within_band | 5387 | 4.71 | 3 | 15 | 58 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | extended_above | extended_below | within_band |
|---|---|---|---|
| extended_above | 94.0% | 0.1% | 5.9% |
| extended_below | 0.1% | 91.3% | 8.6% |
| within_band | 10.6% | 10.4% | 78.9% |

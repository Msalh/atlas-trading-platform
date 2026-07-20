# RE-1 Fact Profile

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-09-30T15:10:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 56490
- **Generated at**: 2026-07-20T12:03:27.987976+00:00
- **Code version**: faacf83cf2ac43c8ac4182629d75a5540bc7215f

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## volume_spike (boolean)

- Computable: 56471  Insufficient data: 19
- True: 14.3% (8082)  False: 48389

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 4232 | 11.43 | 7 | 40 | 89 |
| true | 4044 | 2.00 | 1 | 7 | 17 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 91.6% | 8.4% |
| true | 50.0% | 50.0% |

## displacement (boolean)

- Computable: 56477  Insufficient data: 13
- True: 10.4% (5875)  False: 50602

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 4281 | 11.82 | 7 | 40 | 95 |
| true | 4186 | 1.40 | 1 | 3 | 10 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 91.9% | 8.1% |
| true | 71.2% | 28.8% |

## rejection (boolean)

- Computable: 56490  Insufficient data: 0
- True: 3.0% (1701)  False: 54789

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 1692 | 32.38 | 13 | 126 | 266 |
| true | 1539 | 1.11 | 1 | 2 | 4 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 97.3% | 2.7% |
| true | 90.4% | 9.6% |

## trend_5m (enum)

- Computable: 52519  Insufficient data: 3971
- First-order distribution (value: count):
  - down: 17488 (33.3%)
  - flat: 14227 (27.1%)
  - up: 20804 (39.6%)

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| down | 1208 | 14.48 | 12 | 34 | 116 |
| flat | 2487 | 5.72 | 4 | 15 | 47 |
| up | 1359 | 15.31 | 13 | 38 | 72 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | down | flat | up |
|---|---|---|---|
| down | 93.5% | 6.5% | 0.0% |
| flat | 8.1% | 82.9% | 9.1% |
| up | 0.0% | 6.2% | 93.8% |

## liquidity_sweep (boolean)

- Computable: 56072  Insufficient data: 418
- True: 23.1% (12929)  False: 43143

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 2791 | 15.46 | 6 | 67 | 262 |
| true | 2830 | 4.57 | 4 | 11 | 31 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 93.8% | 6.2% |
| true | 21.4% | 78.6% |

## reclaim (boolean)

- Computable: 56072  Insufficient data: 418
- True: 3.0% (1665)  False: 54407

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| false | 1210 | 44.96 | 11 | 198 | 274 |
| true | 1010 | 1.65 | 2 | 2 | 5 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | false | true |
|---|---|---|
| false | 98.1% | 1.9% |
| true | 60.6% | 39.4% |

## vwap_relationship (enum)

- Computable: 56477  Insufficient data: 13
- First-order distribution (value: count):
  - extended_above: 24892 (44.1%)
  - extended_below: 17465 (30.9%)
  - within_band: 14120 (25.0%)

**Persistence summary** (see RE1_Persistence.md for full run-length distributions):

| value | run count | mean length | median length | p95 length | max length |
|---|---|---|---|---|---|
| extended_above | 1503 | 16.56 | 3 | 83 | 256 |
| extended_below | 1567 | 11.15 | 3 | 58 | 171 |
| within_band | 3060 | 4.61 | 3 | 14 | 58 |

**Transitions** (P(next value | current value), consecutive computable bars only):

| from \ to | extended_above | extended_below | within_band |
|---|---|---|---|
| extended_above | 94.4% | 0.1% | 5.6% |
| extended_below | 0.1% | 91.4% | 8.5% |
| within_band | 10.5% | 11.0% | 78.5% |

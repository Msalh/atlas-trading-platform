# RE-1 Persistence

> **VALIDATION RUN** - this report exists to prove the RE-1 pipeline computes correctly, not to characterize real market behavior. The dataset behind it (1200 bars) is a correctness-validation dataset, not a basis for any market-characteristics or trading conclusion. The same pipeline, unchanged, is designed to be re-run against a much larger historical dataset once one is available.

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2026-07-13T13:05:00+00:00 -> 2026-07-17T21:00:00+00:00
- **Source**: csv:../data/CME_MINI_MNQ.csv
- **Row count**: 1200
- **Generated at**: 2026-07-20T11:44:35.275973+00:00
- **Code version**: 1a97a859c72e2fbd1eed01bf891bf5c35ddd5f6c

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

Full run-length distributions per fact and value - how many consecutive bars a state typically holds before changing. A run never bridges a gap in computability or a data segment boundary.

## volume_spike

### value = false

- Runs: 71  Total bars covered: 1043  Mean length: 14.69  Median: 8  p95: 55  Max: 68

| run length (bars) | number of runs |
|---|---|
| 1 | 10 |
| 2 | 6 |
| 3 | 7 |
| 4 | 4 |
| 5 | 4 |
| 6 | 3 |
| 7 | 1 |
| 8 | 2 |
| 9 | 1 |
| 10 | 2 |
| 11 | 1 |
| 12 | 5 |
| 13 | 2 |
| 17 | 3 |
| 20 | 3 |
| 21 | 2 |
| 22 | 1 |
| 26 | 1 |
| 27 | 1 |
| 29 | 2 |
| 32 | 1 |
| 37 | 1 |
| 44 | 1 |
| 47 | 1 |
| 51 | 1 |
| 55 | 2 |
| 60 | 1 |
| 62 | 1 |
| 68 | 1 |

### value = true

- Runs: 66  Total bars covered: 157  Mean length: 2.38  Median: 1  p95: 8  Max: 11

| run length (bars) | number of runs |
|---|---|
| 1 | 34 |
| 2 | 15 |
| 3 | 5 |
| 4 | 3 |
| 5 | 2 |
| 6 | 1 |
| 7 | 2 |
| 8 | 2 |
| 9 | 1 |
| 11 | 1 |

## displacement

### value = false

- Runs: 76  Total bars covered: 1086  Mean length: 14.29  Median: 8  p95: 64  Max: 77

| run length (bars) | number of runs |
|---|---|
| 1 | 5 |
| 2 | 6 |
| 3 | 7 |
| 4 | 6 |
| 5 | 6 |
| 6 | 4 |
| 7 | 3 |
| 8 | 2 |
| 9 | 3 |
| 10 | 5 |
| 11 | 2 |
| 12 | 1 |
| 13 | 3 |
| 15 | 1 |
| 16 | 1 |
| 17 | 2 |
| 18 | 1 |
| 19 | 1 |
| 22 | 3 |
| 23 | 3 |
| 25 | 2 |
| 39 | 1 |
| 40 | 1 |
| 44 | 1 |
| 47 | 1 |
| 52 | 1 |
| 64 | 1 |
| 65 | 1 |
| 68 | 1 |
| 77 | 1 |

### value = true

- Runs: 72  Total bars covered: 114  Mean length: 1.58  Median: 1  p95: 7  Max: 8

| run length (bars) | number of runs |
|---|---|
| 1 | 57 |
| 2 | 8 |
| 3 | 2 |
| 4 | 1 |
| 7 | 1 |
| 8 | 3 |

## rejection

### value = false

- Runs: 43  Total bars covered: 1158  Mean length: 26.93  Median: 13  p95: 149  Max: 178

| run length (bars) | number of runs |
|---|---|
| 1 | 5 |
| 2 | 2 |
| 3 | 1 |
| 4 | 2 |
| 5 | 2 |
| 6 | 3 |
| 7 | 1 |
| 9 | 2 |
| 10 | 1 |
| 12 | 2 |
| 13 | 1 |
| 15 | 1 |
| 17 | 2 |
| 18 | 1 |
| 20 | 1 |
| 22 | 1 |
| 24 | 1 |
| 26 | 1 |
| 29 | 1 |
| 31 | 1 |
| 32 | 1 |
| 35 | 1 |
| 40 | 1 |
| 42 | 1 |
| 43 | 1 |
| 44 | 2 |
| 46 | 1 |
| 149 | 1 |
| 166 | 1 |
| 178 | 1 |

### value = true

- Runs: 40  Total bars covered: 42  Mean length: 1.05  Median: 1  p95: 1  Max: 3

| run length (bars) | number of runs |
|---|---|
| 1 | 39 |
| 3 | 1 |

## trend_5m

### value = down

- Runs: 29  Total bars covered: 506  Mean length: 17.45  Median: 17  p95: 41  Max: 44

| run length (bars) | number of runs |
|---|---|
| 1 | 3 |
| 3 | 1 |
| 4 | 2 |
| 6 | 2 |
| 7 | 1 |
| 8 | 2 |
| 10 | 2 |
| 15 | 1 |
| 17 | 1 |
| 20 | 1 |
| 23 | 3 |
| 24 | 1 |
| 25 | 1 |
| 28 | 2 |
| 29 | 1 |
| 30 | 1 |
| 32 | 1 |
| 35 | 1 |
| 41 | 1 |
| 44 | 1 |

### value = flat

- Runs: 53  Total bars covered: 277  Mean length: 5.23  Median: 3  p95: 14  Max: 45

| run length (bars) | number of runs |
|---|---|
| 1 | 1 |
| 2 | 14 |
| 3 | 13 |
| 4 | 9 |
| 5 | 5 |
| 6 | 2 |
| 7 | 1 |
| 8 | 1 |
| 10 | 1 |
| 11 | 1 |
| 12 | 1 |
| 13 | 1 |
| 14 | 1 |
| 16 | 1 |
| 45 | 1 |

### value = up

- Runs: 26  Total bars covered: 322  Mean length: 12.38  Median: 11  p95: 22  Max: 30

| run length (bars) | number of runs |
|---|---|
| 1 | 2 |
| 3 | 2 |
| 4 | 1 |
| 6 | 3 |
| 9 | 2 |
| 10 | 2 |
| 11 | 1 |
| 13 | 2 |
| 15 | 1 |
| 17 | 3 |
| 18 | 2 |
| 19 | 1 |
| 22 | 3 |
| 30 | 1 |

## liquidity_sweep

### value = false

- Runs: 56  Total bars covered: 887  Mean length: 15.84  Median: 8  p95: 59  Max: 151

| run length (bars) | number of runs |
|---|---|
| 1 | 9 |
| 2 | 5 |
| 3 | 5 |
| 4 | 2 |
| 5 | 1 |
| 6 | 2 |
| 7 | 3 |
| 8 | 3 |
| 9 | 3 |
| 10 | 3 |
| 11 | 3 |
| 12 | 1 |
| 19 | 1 |
| 20 | 1 |
| 22 | 2 |
| 23 | 2 |
| 24 | 1 |
| 29 | 1 |
| 30 | 2 |
| 42 | 1 |
| 57 | 1 |
| 59 | 2 |
| 71 | 1 |
| 151 | 1 |

### value = true

- Runs: 55  Total bars covered: 303  Mean length: 5.51  Median: 4  p95: 12  Max: 21

| run length (bars) | number of runs |
|---|---|
| 1 | 7 |
| 2 | 1 |
| 3 | 11 |
| 4 | 10 |
| 5 | 4 |
| 6 | 5 |
| 7 | 5 |
| 8 | 3 |
| 9 | 2 |
| 10 | 2 |
| 11 | 1 |
| 12 | 2 |
| 18 | 1 |
| 21 | 1 |

## reclaim

### value = false

- Runs: 21  Total bars covered: 1165  Mean length: 55.48  Median: 28  p95: 188  Max: 189

| run length (bars) | number of runs |
|---|---|
| 1 | 1 |
| 3 | 1 |
| 5 | 1 |
| 8 | 1 |
| 9 | 1 |
| 11 | 4 |
| 22 | 1 |
| 28 | 1 |
| 30 | 1 |
| 36 | 1 |
| 46 | 1 |
| 65 | 1 |
| 72 | 1 |
| 95 | 1 |
| 153 | 1 |
| 171 | 1 |
| 188 | 1 |
| 189 | 1 |

### value = true

- Runs: 16  Total bars covered: 25  Mean length: 1.56  Median: 1  p95: 3  Max: 3

| run length (bars) | number of runs |
|---|---|
| 1 | 8 |
| 2 | 7 |
| 3 | 1 |

## vwap_relationship

### value = extended_above

- Runs: 25  Total bars covered: 379  Mean length: 15.16  Median: 3  p95: 75  Max: 115

| run length (bars) | number of runs |
|---|---|
| 1 | 7 |
| 2 | 3 |
| 3 | 3 |
| 4 | 2 |
| 5 | 2 |
| 9 | 2 |
| 11 | 1 |
| 16 | 1 |
| 30 | 1 |
| 74 | 1 |
| 75 | 1 |
| 115 | 1 |

### value = extended_below

- Runs: 40  Total bars covered: 556  Mean length: 13.90  Median: 2  p95: 64  Max: 126

| run length (bars) | number of runs |
|---|---|
| 1 | 17 |
| 2 | 4 |
| 3 | 3 |
| 5 | 1 |
| 6 | 2 |
| 9 | 1 |
| 10 | 1 |
| 11 | 1 |
| 12 | 1 |
| 14 | 1 |
| 15 | 1 |
| 16 | 1 |
| 27 | 1 |
| 54 | 1 |
| 63 | 1 |
| 64 | 1 |
| 84 | 1 |
| 126 | 1 |

### value = within_band

- Runs: 66  Total bars covered: 265  Mean length: 4.02  Median: 3  p95: 12  Max: 16

| run length (bars) | number of runs |
|---|---|
| 1 | 21 |
| 2 | 10 |
| 3 | 10 |
| 4 | 8 |
| 5 | 1 |
| 6 | 1 |
| 7 | 3 |
| 8 | 1 |
| 9 | 4 |
| 10 | 1 |
| 11 | 2 |
| 12 | 2 |
| 14 | 1 |
| 16 | 1 |

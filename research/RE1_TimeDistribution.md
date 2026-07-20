# RE-1 Time Distribution

> **VALIDATION RUN** - this report exists to prove the RE-1 pipeline computes correctly, not to characterize real market behavior. The dataset behind it (1200 bars) is a correctness-validation dataset, not a basis for any market-characteristics or trading conclusion. The same pipeline, unchanged, is designed to be re-run against a much larger historical dataset once one is available.

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2026-07-13T13:05:00+00:00 -> 2026-07-17T21:00:00+00:00
- **Source**: csv:../data/CME_MINI_MNQ.csv
- **Row count**: 1200
- **Generated at**: 2026-07-20T11:44:35.275973+00:00
- **Code version**: 1a97a859c72e2fbd1eed01bf891bf5c35ddd5f6c

No trading conclusions. No alpha claims. No expectancy. No forward returns.
This is a statistical characterization of the Market State only.

## By session

| bucket | bar count | P(displacement=True) | P(liquidity_sweep=True) | P(reclaim=True) | P(rejection=True) | P(volume_spike=True) |
|---|---|---|---|---|---|---|
| OVERNIGHT | 810 | 8.9% | 33.1% | 1.4% | 4.7% | 12.1% |
| RTH | 390 | 10.8% | 9.7% | 3.6% | 1.0% | 15.1% |

**trend_5m value counts by bucket:**

| bucket | down | flat | up |
|---|---|---|---|
| OVERNIGHT | 303 | 205 | 220 |
| RTH | 203 | 72 | 102 |

**vwap_relationship value counts by bucket:**

| bucket | extended_above | extended_below | within_band |
|---|---|---|---|
| OVERNIGHT | 269 | 346 | 195 |
| RTH | 110 | 210 | 70 |

## By hour (America/Chicago)

| bucket | bar count | P(displacement=True) | P(liquidity_sweep=True) | P(reclaim=True) | P(rejection=True) | P(volume_spike=True) |
|---|---|---|---|---|---|---|
| 00:00 | 48 | 16.7% | 45.8% | 0.0% | 10.4% | 20.8% |
| 01:00 | 48 | 10.4% | 31.2% | 6.2% | 0.0% | 4.2% |
| 02:00 | 48 | 8.3% | 35.4% | 4.2% | 8.3% | 4.2% |
| 03:00 | 48 | 10.4% | 39.6% | 0.0% | 4.2% | 16.7% |
| 04:00 | 48 | 2.1% | 0.0% | 0.0% | 0.0% | 0.0% |
| 05:00 | 48 | 8.3% | 0.0% | 0.0% | 0.0% | 14.6% |
| 06:00 | 48 | 8.3% | 31.2% | 0.0% | 2.1% | 27.1% |
| 07:00 | 48 | 14.6% | 10.4% | 4.2% | 0.0% | 25.0% |
| 08:00 | 59 | 37.3% | 3.5% | 1.8% | 1.7% | 54.2% |
| 09:00 | 60 | 30.0% | 30.0% | 13.3% | 0.0% | 36.7% |
| 10:00 | 60 | 0.0% | 11.7% | 0.0% | 1.7% | 0.0% |
| 11:00 | 60 | 1.7% | 5.0% | 3.3% | 1.7% | 1.7% |
| 12:00 | 60 | 0.0% | 8.3% | 5.0% | 1.7% | 0.0% |
| 13:00 | 60 | 0.0% | 0.0% | 0.0% | 0.0% | 1.7% |
| 14:00 | 60 | 3.3% | 5.0% | 0.0% | 0.0% | 13.3% |
| 15:00 | 60 | 5.0% | 53.3% | 6.7% | 5.0% | 3.3% |
| 16:00 | 5 | 0.0% | 20.0% | 0.0% | 20.0% | 0.0% |
| 17:00 | 44 | 6.8% | 36.1% | 0.0% | 9.1% | 4.5% |
| 18:00 | 48 | 12.5% | 56.2% | 0.0% | 8.3% | 22.9% |
| 19:00 | 48 | 27.1% | 72.9% | 0.0% | 8.3% | 45.8% |
| 20:00 | 48 | 10.4% | 45.8% | 0.0% | 4.2% | 0.0% |
| 21:00 | 48 | 2.1% | 39.6% | 0.0% | 6.2% | 0.0% |
| 22:00 | 48 | 2.1% | 22.9% | 0.0% | 4.2% | 2.1% |
| 23:00 | 48 | 2.1% | 25.0% | 0.0% | 6.2% | 2.1% |

**trend_5m value counts by bucket:**

| bucket | down | flat | up |
|---|---|---|---|
| 00:00 | 13 | 22 | 13 |
| 01:00 | 12 | 16 | 20 |
| 02:00 | 29 | 15 | 4 |
| 03:00 | 36 | 12 | 0 |
| 04:00 | 12 | 19 | 17 |
| 05:00 | 15 | 19 | 14 |
| 06:00 | 16 | 21 | 11 |
| 07:00 | 30 | 10 | 8 |
| 08:00 | 16 | 9 | 23 |
| 09:00 | 27 | 17 | 8 |
| 10:00 | 20 | 13 | 27 |
| 11:00 | 41 | 7 | 12 |
| 12:00 | 24 | 10 | 26 |
| 13:00 | 29 | 10 | 21 |
| 14:00 | 50 | 9 | 1 |
| 15:00 | 37 | 12 | 11 |
| 16:00 | 1 | 2 | 2 |
| 17:00 | 0 | 0 | 0 |
| 18:00 | 8 | 4 | 4 |
| 19:00 | 20 | 10 | 18 |
| 20:00 | 24 | 9 | 15 |
| 21:00 | 21 | 9 | 18 |
| 22:00 | 16 | 7 | 25 |
| 23:00 | 9 | 15 | 24 |

**vwap_relationship value counts by bucket:**

| bucket | extended_above | extended_below | within_band |
|---|---|---|---|
| 00:00 | 30 | 12 | 6 |
| 01:00 | 26 | 12 | 10 |
| 02:00 | 24 | 22 | 2 |
| 03:00 | 13 | 25 | 10 |
| 04:00 | 13 | 24 | 11 |
| 05:00 | 12 | 28 | 8 |
| 06:00 | 12 | 26 | 10 |
| 07:00 | 14 | 30 | 4 |
| 08:00 | 15 | 38 | 6 |
| 09:00 | 10 | 24 | 26 |
| 10:00 | 13 | 25 | 22 |
| 11:00 | 24 | 36 | 0 |
| 12:00 | 24 | 36 | 0 |
| 13:00 | 19 | 31 | 10 |
| 14:00 | 14 | 37 | 9 |
| 15:00 | 12 | 34 | 14 |
| 16:00 | 1 | 3 | 1 |
| 17:00 | 0 | 9 | 35 |
| 18:00 | 7 | 18 | 23 |
| 19:00 | 17 | 16 | 15 |
| 20:00 | 17 | 20 | 11 |
| 21:00 | 13 | 17 | 18 |
| 22:00 | 23 | 21 | 4 |
| 23:00 | 26 | 12 | 10 |

## By weekday (America/Chicago)

| bucket | bar count | P(displacement=True) | P(liquidity_sweep=True) | P(reclaim=True) | P(rejection=True) | P(volume_spike=True) |
|---|---|---|---|---|---|---|
| Monday | 179 | 12.3% | 26.3% | 1.7% | 5.0% | 14.0% |
| Tuesday | 276 | 6.2% | 27.0% | 1.8% | 2.9% | 13.8% |
| Wednesday | 276 | 10.9% | 13.9% | 2.2% | 1.4% | 14.1% |
| Thursday | 276 | 10.9% | 38.0% | 2.9% | 5.8% | 12.3% |
| Friday | 193 | 7.8% | 21.2% | 1.6% | 2.6% | 10.9% |

**trend_5m value counts by bucket:**

| bucket | down | flat | up |
|---|---|---|---|
| Monday | 74 | 34 | 33 |
| Tuesday | 47 | 85 | 125 |
| Wednesday | 105 | 71 | 81 |
| Thursday | 174 | 57 | 26 |
| Friday | 106 | 30 | 57 |

**vwap_relationship value counts by bucket:**

| bucket | extended_above | extended_below | within_band |
|---|---|---|---|
| Monday | 18 | 103 | 58 |
| Tuesday | 250 | 0 | 26 |
| Wednesday | 66 | 107 | 103 |
| Thursday | 8 | 226 | 42 |
| Friday | 37 | 120 | 36 |

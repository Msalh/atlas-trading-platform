# RE-2 Context Profile

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T14:18:36.013255+00:00
- **Code version**: 806e4f1ae2386a68207192089ab303d77c05fa66

Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate content. trend_1m is never used - it is not a registered Rule Engine fact.

At each offset, bar-level availability (was the offset bar inside the same segment) and fact-level computability (was this specific registered fact computable at that bar) are tracked independently - one fact's InsufficientData never marks the whole context snapshot unavailable. Descriptive state transitions only - not outcome or return analysis.

## displacement_with_volume_confirmation

### Offset: -1 (n episodes=5270)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 5237 | 33 | 5237 | 0 | 24.9% |
| displacement | 5237 | 33 | 5237 | 0 | 3.9% |
| rejection | 5237 | 33 | 5237 | 0 | 2.8% |
| trend_5m | 5237 | 33 | 5083 | 154 | down=1825, flat=1462, up=1796 |
| liquidity_sweep | 5237 | 33 | 5237 | 0 | 21.7% |
| reclaim | 5237 | 33 | 5237 | 0 | 3.1% |
| vwap_relationship | 5237 | 33 | 5237 | 0 | extended_above=2319, extended_below=1710, within_band=1208 |

Session at this offset: OVERNIGHT=4107, RTH=1130

### Offset: activation (n episodes=5270)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 5270 | 0 | 5270 | 0 | 100.0% |
| displacement | 5270 | 0 | 5270 | 0 | 100.0% |
| rejection | 5270 | 0 | 5270 | 0 | 3.7% |
| trend_5m | 5270 | 0 | 5090 | 180 | down=1874, flat=1479, up=1737 |
| liquidity_sweep | 5270 | 0 | 5237 | 33 | 34.5% |
| reclaim | 5270 | 0 | 5237 | 33 | 5.0% |
| vwap_relationship | 5270 | 0 | 5270 | 0 | extended_above=2273, extended_below=1839, within_band=1158 |

Session at this offset: OVERNIGHT=3938, RTH=1332

### Offset: +1 (n episodes=5270)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 5268 | 2 | 5268 | 0 | 49.8% |
| displacement | 5268 | 2 | 5268 | 0 | 27.5% |
| rejection | 5268 | 2 | 5268 | 0 | 5.0% |
| trend_5m | 5268 | 2 | 5104 | 164 | down=1937, flat=1448, up=1719 |
| liquidity_sweep | 5268 | 2 | 5235 | 33 | 37.3% |
| reclaim | 5268 | 2 | 5235 | 33 | 5.7% |
| vwap_relationship | 5268 | 2 | 5268 | 0 | extended_above=2263, extended_below=1816, within_band=1189 |

Session at this offset: OVERNIGHT=3845, RTH=1423

### Offset: +3 (n episodes=5270)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 5268 | 2 | 5268 | 0 | 30.2% |
| displacement | 5268 | 2 | 5268 | 0 | 18.5% |
| rejection | 5268 | 2 | 5268 | 0 | 4.0% |
| trend_5m | 5268 | 2 | 5124 | 144 | down=2087, flat=1300, up=1737 |
| liquidity_sweep | 5268 | 2 | 5268 | 0 | 32.4% |
| reclaim | 5268 | 2 | 5268 | 0 | 3.3% |
| vwap_relationship | 5268 | 2 | 5268 | 0 | extended_above=2270, extended_below=1783, within_band=1215 |

Session at this offset: OVERNIGHT=3974, RTH=1294

## liquidity_sweep_with_volume_confirmation

### Offset: -1 (n episodes=2970)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 2970 | 0 | 2969 | 1 | 23.1% |
| displacement | 2970 | 0 | 2970 | 0 | 19.6% |
| rejection | 2970 | 0 | 2970 | 0 | 3.7% |
| trend_5m | 2970 | 0 | 2774 | 196 | down=962, flat=694, up=1118 |
| liquidity_sweep | 2970 | 0 | 2966 | 4 | 39.2% |
| reclaim | 2970 | 0 | 2966 | 4 | 4.3% |
| vwap_relationship | 2970 | 0 | 2970 | 0 | extended_above=1491, extended_below=1113, within_band=366 |

Session at this offset: OVERNIGHT=2422, RTH=548

### Offset: activation (n episodes=2970)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 2970 | 0 | 2970 | 0 | 100.0% |
| displacement | 2970 | 0 | 2970 | 0 | 59.6% |
| rejection | 2970 | 0 | 2970 | 0 | 15.7% |
| trend_5m | 2970 | 0 | 2781 | 189 | down=996, flat=640, up=1145 |
| liquidity_sweep | 2970 | 0 | 2970 | 0 | 100.0% |
| reclaim | 2970 | 0 | 2970 | 0 | 17.1% |
| vwap_relationship | 2970 | 0 | 2970 | 0 | extended_above=1478, extended_below=1185, within_band=307 |

Session at this offset: OVERNIGHT=2406, RTH=564

### Offset: +1 (n episodes=2970)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 2968 | 2 | 2968 | 0 | 45.2% |
| displacement | 2968 | 2 | 2968 | 0 | 25.9% |
| rejection | 2968 | 2 | 2968 | 0 | 11.7% |
| trend_5m | 2968 | 2 | 2800 | 168 | down=1058, flat=550, up=1192 |
| liquidity_sweep | 2968 | 2 | 2968 | 0 | 89.6% |
| reclaim | 2968 | 2 | 2968 | 0 | 11.7% |
| vwap_relationship | 2968 | 2 | 2968 | 0 | extended_above=1466, extended_below=1131, within_band=371 |

Session at this offset: OVERNIGHT=2388, RTH=580

### Offset: +3 (n episodes=2970)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 2966 | 4 | 2966 | 0 | 29.0% |
| displacement | 2966 | 4 | 2966 | 0 | 17.6% |
| rejection | 2966 | 4 | 2966 | 0 | 6.1% |
| trend_5m | 2966 | 4 | 2821 | 145 | down=1133, flat=451, up=1237 |
| liquidity_sweep | 2966 | 4 | 2966 | 0 | 57.9% |
| reclaim | 2966 | 4 | 2966 | 0 | 4.3% |
| vwap_relationship | 2966 | 4 | 2966 | 0 | extended_above=1431, extended_below=1099, within_band=436 |

Session at this offset: OVERNIGHT=2405, RTH=561

## sustained_displacement_streak

### Offset: -1 (n episodes=1708)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 1708 | 0 | 1707 | 1 | 81.7% |
| displacement | 1708 | 0 | 1708 | 0 | 100.0% |
| rejection | 1708 | 0 | 1708 | 0 | 3.4% |
| trend_5m | 1708 | 0 | 1640 | 68 | down=632, flat=474, up=534 |
| liquidity_sweep | 1708 | 0 | 1672 | 36 | 31.9% |
| reclaim | 1708 | 0 | 1672 | 36 | 6.2% |
| vwap_relationship | 1708 | 0 | 1708 | 0 | extended_above=670, extended_below=655, within_band=383 |

Session at this offset: OVERNIGHT=1124, RTH=584

### Offset: activation (n episodes=1708)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 1708 | 0 | 1707 | 1 | 85.8% |
| displacement | 1708 | 0 | 1708 | 0 | 100.0% |
| rejection | 1708 | 0 | 1708 | 0 | 6.0% |
| trend_5m | 1708 | 0 | 1644 | 64 | down=664, flat=482, up=498 |
| liquidity_sweep | 1708 | 0 | 1672 | 36 | 42.0% |
| reclaim | 1708 | 0 | 1672 | 36 | 8.3% |
| vwap_relationship | 1708 | 0 | 1708 | 0 | extended_above=667, extended_below=662, within_band=379 |

Session at this offset: OVERNIGHT=1004, RTH=704

### Offset: +1 (n episodes=1708)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 1705 | 3 | 1704 | 1 | 57.0% |
| displacement | 1705 | 3 | 1705 | 0 | 36.7% |
| rejection | 1705 | 3 | 1705 | 0 | 6.0% |
| trend_5m | 1705 | 3 | 1644 | 61 | down=688, flat=467, up=489 |
| liquidity_sweep | 1705 | 3 | 1705 | 0 | 47.6% |
| reclaim | 1705 | 3 | 1705 | 0 | 9.5% |
| vwap_relationship | 1705 | 3 | 1705 | 0 | extended_above=660, extended_below=639, within_band=406 |

Session at this offset: OVERNIGHT=1054, RTH=651

### Offset: +3 (n episodes=1708)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 1704 | 4 | 1703 | 1 | 38.9% |
| displacement | 1704 | 4 | 1704 | 0 | 25.8% |
| rejection | 1704 | 4 | 1704 | 0 | 3.3% |
| trend_5m | 1704 | 4 | 1648 | 56 | down=740, flat=392, up=516 |
| liquidity_sweep | 1704 | 4 | 1704 | 0 | 34.0% |
| reclaim | 1704 | 4 | 1704 | 0 | 5.2% |
| vwap_relationship | 1704 | 4 | 1704 | 0 | extended_above=673, extended_below=634, within_band=397 |

Session at this offset: OVERNIGHT=1063, RTH=641

## vwap_extension_with_volume_confirmation

### Offset: -1 (n episodes=6331)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 6321 | 10 | 6320 | 1 | 9.4% |
| displacement | 6321 | 10 | 6321 | 0 | 10.6% |
| rejection | 6321 | 10 | 6321 | 0 | 1.9% |
| trend_5m | 6321 | 10 | 6111 | 210 | down=2084, flat=1746, up=2281 |
| liquidity_sweep | 6321 | 10 | 6318 | 3 | 22.0% |
| reclaim | 6321 | 10 | 6318 | 3 | 2.6% |
| vwap_relationship | 6321 | 10 | 6321 | 0 | extended_above=2933, extended_below=2022, within_band=1366 |

Session at this offset: OVERNIGHT=5115, RTH=1206

### Offset: activation (n episodes=6331)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 6331 | 0 | 6331 | 0 | 100.0% |
| displacement | 6331 | 0 | 6331 | 0 | 55.8% |
| rejection | 6331 | 0 | 6331 | 0 | 4.6% |
| trend_5m | 6331 | 0 | 6121 | 210 | down=2147, flat=1707, up=2267 |
| liquidity_sweep | 6331 | 0 | 6319 | 12 | 35.3% |
| reclaim | 6331 | 0 | 6319 | 12 | 3.6% |
| vwap_relationship | 6331 | 0 | 6331 | 0 | extended_above=3582, extended_below=2749 |

Session at this offset: OVERNIGHT=5033, RTH=1298

### Offset: +1 (n episodes=6331)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 6329 | 2 | 6329 | 0 | 43.0% |
| displacement | 6329 | 2 | 6329 | 0 | 23.8% |
| rejection | 6329 | 2 | 6329 | 0 | 5.7% |
| trend_5m | 6329 | 2 | 6140 | 189 | down=2231, flat=1628, up=2281 |
| liquidity_sweep | 6329 | 2 | 6319 | 10 | 38.4% |
| reclaim | 6329 | 2 | 6319 | 10 | 4.0% |
| vwap_relationship | 6329 | 2 | 6329 | 0 | extended_above=3275, extended_below=2431, within_band=623 |

Session at this offset: OVERNIGHT=4886, RTH=1443

### Offset: +3 (n episodes=6331)

| fact | bar available | bar unavailable | computable | insufficient | true rate / value counts |
|---|---|---|---|---|---|
| volume_spike | 6327 | 4 | 6327 | 0 | 28.2% |
| displacement | 6327 | 4 | 6327 | 0 | 17.2% |
| rejection | 6327 | 4 | 6327 | 0 | 4.0% |
| trend_5m | 6327 | 4 | 6165 | 162 | down=2433, flat=1383, up=2349 |
| liquidity_sweep | 6327 | 4 | 6327 | 0 | 35.9% |
| reclaim | 6327 | 4 | 6327 | 0 | 3.6% |
| vwap_relationship | 6327 | 4 | 6327 | 0 | extended_above=3135, extended_below=2265, within_band=927 |

Session at this offset: OVERNIGHT=5029, RTH=1298

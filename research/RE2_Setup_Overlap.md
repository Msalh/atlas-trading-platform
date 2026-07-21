# RE-2 Setup Overlap

- **Symbol**: MNQ1!  **Timeframe**: 5m
- **Requested range**: 2025-03-02T23:05:00+00:00 -> 2026-07-20T11:35:00+00:00
- **Source**: csv:../data/CME_03_03_25_16_06_25.csv,../data/CME_16_06_25_30_09_25.csv,../data/CME_01_10_31_12.csv,../data/CME_01_01_05_04.csv,../data/CME_06_04_20_07.csv
- **Row count**: 97858
- **Generated at**: 2026-07-20T14:18:36.013255+00:00
- **Code version**: 806e4f1ae2386a68207192089ab303d77c05fa66

Descriptive Setup Profiling only. No profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate content. trend_1m is never used - it is not a registered Rule Engine fact.

Five separately defined metrics per pair - never a single undefined "overlap" number. `relationship` distinguishes LOGICALLY_IMPLIED (proven from the setup definitions), SHARED_INPUTS_ONLY (inputs overlap, no implication proven), EMPIRICAL (no shared inputs, any relationship found is a genuine finding), and UNKNOWN.

## displacement_with_volume_confirmation x liquidity_sweep_with_volume_confirmation

**Relationship**: `shared_inputs_only` - Both require volume_spike=True (shared input), but their primary facts - displacement (range/ATR-based, single bar) and liquidity_sweep (reference-level breach across its own window) - have no established implication relationship in either direction at the fact level (only rejection/reclaim => liquidity_sweep is proven, per rule-fact-inventory.md's 'Fact hierarchy within this family'; displacement is unrelated to that family). Neither setup's detected=True forces the other's.

**1. Concurrent active-bar overlap** (n jointly computable=97089): P(A)=8.0% P(B)=5.4% P(A and B)=3.0% lift=6.97 correlation=0.421 P(A|B)=55.6% Jaccard=0.290
**2. Same-bar activation overlap**: 1447 shared / 5270 A-activations (27.5%), 2970 B-activations (48.7%)
**3. Temporal episode intersection**: 2131 overlapping episode pairs; 39.8% of A's 5270 episodes, 66.5% of B's 2970 episodes
**4. Full episode containment**: A fully inside B: 1703  B fully inside A: 1184
**5. Activation proximity**: <= 5min: A-with-nearby-B=1890, B-with-nearby-A=1880; <= 15min: A-with-nearby-B=2431, B-with-nearby-A=2306; <= 30min: A-with-nearby-B=2888, B-with-nearby-A=2565

## displacement_with_volume_confirmation x sustained_displacement_streak

**Relationship**: `shared_inputs_only` - Both read displacement (shared input), but the predicates differ in two independent ways: displacement_with_volume_confirmation additionally requires volume_spike=True on the same bar, which sustained_displacement_streak never checks at all; sustained_displacement_streak additionally requires displacement=True on >=2 CONSECUTIVE bars ending at the current one, which displacement_with_volume_confirmation never checks (it looks at exactly one bar). displacement=True with volume_spike=True on an isolated bar (displacement=False the bar before) satisfies the first setup but not the second; a 2+ bar displacement streak with volume_spike=False throughout satisfies the second but not the first. Sharing an input fact does not make these logically related - the explicit case amendment 5 named.

**1. Concurrent active-bar overlap** (n jointly computable=97445): P(A)=8.0% P(B)=3.1% P(A and B)=2.8% lift=11.31 correlation=0.542 P(A|B)=90.0% Jaccard=0.337
**2. Same-bar activation overlap**: 180 shared / 5270 A-activations (3.4%), 1708 B-activations (10.5%)
**3. Temporal episode intersection**: 1486 overlapping episode pairs; 28.2% of A's 5270 episodes, 86.8% of B's 1708 episodes
**4. Full episode containment**: A fully inside B: 202  B fully inside A: 1422
**5. Activation proximity**: <= 5min: A-with-nearby-B=1592, B-with-nearby-A=1580; <= 15min: A-with-nearby-B=1936, B-with-nearby-A=1591; <= 30min: A-with-nearby-B=2412, B-with-nearby-A=1616

## displacement_with_volume_confirmation x vwap_extension_with_volume_confirmation

**Relationship**: `shared_inputs_only` - Both require volume_spike=True (shared input); their other primary facts - displacement and vwap_relationship - are computed from unrelated MarketState fields with no known implication relationship. Neither setup's detected=True forces the other's.

**1. Concurrent active-bar overlap** (n jointly computable=97801): P(A)=8.0% P(B)=11.7% P(A and B)=6.2% lift=6.67 correlation=0.608 P(A|B)=53.1% Jaccard=0.463
**2. Same-bar activation overlap**: 3260 shared / 5270 A-activations (61.9%), 6331 B-activations (51.5%)
**3. Temporal episode intersection**: 4384 overlapping episode pairs; 81.4% of A's 5270 episodes, 63.0% of B's 6331 episodes
**4. Full episode containment**: A fully inside B: 3895  B fully inside A: 2409
**5. Activation proximity**: <= 5min: A-with-nearby-B=3909, B-with-nearby-A=3917; <= 15min: A-with-nearby-B=4520, B-with-nearby-A=4705; <= 30min: A-with-nearby-B=4861, B-with-nearby-A=5341

## liquidity_sweep_with_volume_confirmation x sustained_displacement_streak

**Relationship**: `empirical` - No shared input facts at all: liquidity_sweep_with_volume_confirmation reads liquidity_sweep and volume_spike; sustained_displacement_streak reads displacement only. Any co-occurrence found between these two is a genuine empirical finding, not implied by either setup's definition.

**1. Concurrent active-bar overlap** (n jointly computable=97089): P(A)=5.4% P(B)=3.1% P(A and B)=1.2% lift=7.46 correlation=0.275 P(A|B)=40.4% Jaccard=0.171
**2. Same-bar activation overlap**: 256 shared / 2970 A-activations (8.6%), 1708 B-activations (15.0%)
**3. Temporal episode intersection**: 780 overlapping episode pairs; 25.7% of A's 2970 episodes, 43.9% of B's 1708 episodes
**4. Full episode containment**: A fully inside B: 254  B fully inside A: 534
**5. Activation proximity**: <= 5min: A-with-nearby-B=710, B-with-nearby-A=704; <= 15min: A-with-nearby-B=976, B-with-nearby-A=897; <= 30min: A-with-nearby-B=1253, B-with-nearby-A=1043

## liquidity_sweep_with_volume_confirmation x vwap_extension_with_volume_confirmation

**Relationship**: `shared_inputs_only` - Both require volume_spike=True (shared input); liquidity_sweep and vwap_relationship have no known implication relationship. Neither setup's detected=True forces the other's.

**1. Concurrent active-bar overlap** (n jointly computable=97089): P(A)=5.4% P(B)=11.8% P(A and B)=4.8% lift=7.44 correlation=0.564 P(A|B)=40.4% Jaccard=0.382
**2. Same-bar activation overlap**: 2128 shared / 2970 A-activations (71.6%), 6331 B-activations (33.6%)
**3. Temporal episode intersection**: 2764 overlapping episode pairs; 91.4% of A's 2970 episodes, 42.7% of B's 6331 episodes
**4. Full episode containment**: A fully inside B: 2498  B fully inside A: 2079
**5. Activation proximity**: <= 5min: A-with-nearby-B=2486, B-with-nearby-A=2494; <= 15min: A-with-nearby-B=2749, B-with-nearby-A=3003; <= 30min: A-with-nearby-B=2863, B-with-nearby-A=3545

## sustained_displacement_streak x vwap_extension_with_volume_confirmation

**Relationship**: `empirical` - No shared input facts at all: sustained_displacement_streak reads displacement only; vwap_extension_with_volume_confirmation reads vwap_relationship and volume_spike. Any co-occurrence found between these two is a genuine empirical finding, not implied by either setup's definition.

**1. Concurrent active-bar overlap** (n jointly computable=97445): P(A)=3.1% P(B)=11.8% P(A and B)=2.2% lift=6.00 correlation=0.327 P(A|B)=18.6% Jaccard=0.173
**2. Same-bar activation overlap**: 281 shared / 1708 A-activations (16.5%), 6331 B-activations (4.4%)
**3. Temporal episode intersection**: 1300 overlapping episode pairs; 73.1% of A's 1708 episodes, 19.5% of B's 6331 episodes
**4. Full episode containment**: A fully inside B: 1004  B fully inside A: 260
**5. Activation proximity**: <= 5min: A-with-nearby-B=1125, B-with-nearby-A=1161; <= 15min: A-with-nearby-B=1429, B-with-nearby-A=1747; <= 30min: A-with-nearby-B=1546, B-with-nearby-A=2361

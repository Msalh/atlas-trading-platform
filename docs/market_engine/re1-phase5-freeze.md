# RE-1 (Research Engine Phase 1) — Freeze Document

**Status: RE-1 is complete and frozen as of this document, unless a genuine correctness defect is discovered in the pipeline itself.**

## Final dataset

| # | File | Rows loaded | New after dedup |
|---|---|---|---|
| 1 | `data/CME_03_03_25_16_06_25.csv` | 20,376 | 20,376 |
| 2 | `data/CME_16_06_25_30_09_25.csv` | 21,062 | 21,062 |
| 3 | `data/CME_01_10_31_12.csv` | 17,743 | 17,673 |
| 4 | `data/CME_01_01_05_04.csv` | 18,193 | 18,028 |
| 5 | `data/CME_06_04_20_07.csv` | 20,719 | 20,719 |

- **Final row count**: 97,858 unique bars (98,093 raw, 235 identical duplicates removed across file overlaps, 0 conflicts)
- **Final date range**: `2025-03-02T23:05:00+00:00` → `2026-07-20T11:35:00+00:00` (bar-close)
- **Symbol / timeframe**: `MNQ1!` / `5m`
- **Bar-open shift**: applied throughout (`--assume-bar-open-time`), per Sprint 31 Task 3's proven bar-open/bar-close convention

## Code version

`a907325fbb357097fb0e8e064d46772e2b719964` — embedded in every RE1_*.md report's manifest header via `atlas.research.service.current_code_version()`.

## Reports (all under `research/`, all regenerated against the code version above)

- `RE1_Fact_Profile.md`
- `RE1_RuleRelationships.md`
- `RE1_ConditionalProbability.md`
- `RE1_TimeDistribution.md`
- `RE1_Persistence.md`
- `RE1_Research_Notes.md` (summary reading of the above — introduces no new calculations)

## Supporting evidence documents (`docs/market_engine/`)

- `re1-5file-phase3-certification-report.md` — full Phase 3 certification (§1–§12: file inspection, merge/conflict audit, gap classification, boundary audit, ATR/trend_1m root-cause findings, VWAP precision samples, instrument-identity/contract-roll limitations, final verdict)
- `sprint31-task8-phase3-cert-5file-raw.txt` — raw certifier tool output
- `re1-5file-run-output.txt` — raw `run_statistical_profile.py` output for this final run

## Tests

1034 passed, 1 skipped (pre-existing, unrelated to this sprint), full suite, no regressions. Ruff clean except one pre-existing, out-of-scope `F401` in `scripts/dev_seed_server.py` (present before this sprint, untouched by it).

New/changed this sprint:
- `live/tests/test_certify_historical_dataset.py` — 42 tests (36 pre-existing + 6 new: `TestMarketDataIntegrity`'s two warmup-cluster-scaling tests, `TestFeatureIntegrity`'s three trend-threshold tests already existed from earlier work in this arc; this round added the multi-cluster scaling regression tests specifically)
- `live/tests/test_run_statistical_profile.py` — 6 tests, unchanged this round (already covered the merge/conflict logic Phase 2 reused)
- `live/atlas/research/statistical_profiling/` — the pure computation core, unchanged since its original implementation; no defect was found in it by the five-file expansion, so per the standing instruction it was never modified

## Known limitations (carried forward, disclosed, not blocking)

1. **`trend_1m` unreliable before 2025-07-20** — a TradingView 1-minute-data lookback boundary (~365 days before the export date), not a pipeline defect. Does not affect any RE-1 report (raw wire field, never read by the 7 registered Rule Engine facts).
2. **The merged dataset's formal certifier verdict is REJECTED** (one FAIL: `trend_1m`, per the strict-AND certification rule this project deliberately does not weaken). RE-1's own reports remain valid because that FAIL sits entirely outside RE-1's scope — see the certification report's §12 for the full reasoning. Any future work reading `trend_1m` directly must treat that field as unverified before 2025-07-20.
3. **No per-instrument tick-size/roll registry** exists in this codebase (`TICK_SIZE = 0.25` global constant) — standing architectural debt from before this sprint, unchanged by it.
4. **No independent contract-roll detection** — `MNQ1!` is TradingView's own continuous-contract construction; no discontinuity was found at any file boundary, but this project cannot independently confirm individual roll dates.
5. **Symbol/timeframe are CLI-asserted**, not extracted from the CSVs (TradingView's chart-export carries no symbol column) — established since Sprint 29A.6, unchanged.

## Scope discipline maintained

Every RE-1 report and this freeze document describe the Market State's own statistical properties only: fact frequency, persistence, pairwise co-occurrence, conditional probability, and time/session distribution. No report contains a profitability, expectancy, alpha, or forward-return claim. `RE1_Research_Notes.md` explicitly separates structural fact relationships (proven from the Rule Engine's own fact definitions) from genuinely empirical ones, and flags the one relationship (`volume_spike × displacement`) strong enough to be worth a dedicated RE-2 hypothesis if RE-2's scope later extends to joint-fact conditioning.

## Statement

RE-1's five deliverables have been built, validated on a small dataset, and now re-run to completion on the full 97,858-bar, five-file, ~2025-03-02 to 2026-07-20 dataset. The statistical-profiling pipeline (`atlas.research.statistical_profiling`) is source-agnostic and required no changes across the small-dataset validation run, the three-file expansion, or this final five-file expansion — confirming the architectural goal stated at RE-1's outset (the same pipeline unchanged across dataset sizes). The one code change made during this expansion (`certify_historical_dataset.py`'s warmup-tolerance scaling) was to the certifier tool, not the statistical-profiling core, and was made only after real, cluster-level evidence justified it.

**RE-1 is complete and frozen. No further RE-1 work is planned unless a correctness defect is discovered in this pipeline. RE-2 has not been started as part of this change set, per explicit instruction.**

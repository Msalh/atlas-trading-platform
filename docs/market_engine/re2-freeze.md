# RE-2 (Research Engine Phase 2) — Freeze Document

**Status: RE-2 is complete and frozen as of this document, unless a genuine correctness defect is discovered in the pipeline itself.**

## Package / file list

```
live/atlas/research/setup_profiling/
    __init__.py         - scope docstring (descriptive only, no trend_1m)
    models.py            - SetupEpisode, ActivationEvent, RegisteredFactSnapshot, and one
                            dataclass per report (SetupProfile, SetupTimeDistribution,
                            SetupClustering, SetupOverlap, SetupContextProfile, SetupTransitions)
    relationships.py      - centralized, typed SetupRelationshipMetadata for every
                            currently-registered setup pair, validated at import time
    service.py            - pure computation core: episode construction, computability
                            evidence, and all six report builders, sharing one Rule/Setup
                            Engine evaluation pass per input bar
    reports.py             - markdown rendering for the six computed reports (thin,
                            mechanical templates - no computation happens here)

live/scripts/run_setup_profile.py   - CLI runner, reuses run_statistical_profile
                                       .load_and_merge_states unchanged

live/tests/test_setup_profiling.py       - 27 focused tests (episode construction/
                                            termination/censoring, segment-boundary
                                            non-bridging, overlap sweep, clustering,
                                            transition censoring, transition-matrix
                                            denominator documentation)
live/tests/test_setup_relationships.py    - 7 tests proving the relationship metadata
                                             never marks a shared-input pair as
                                             LOGICALLY_IMPLIED
```

## Dataset identity

Same frozen five-file dataset RE-1 certified and froze - unchanged, no new data ingested for RE-2.

- **Symbol / timeframe**: `MNQ1!` / `5m`
- **Row count**: 97,858 unique bars
- **Date range**: `2025-03-02T23:05:00+00:00` -> `2026-07-20T11:35:00+00:00`
- **Segments**: 359 (matches RE-1's certified 358-gap count)

## Code version

`806e4f1ae2386a68207192089ab303d77c05fa66` - embedded in every RE2_*.md report's manifest header.

## Reports (all under `research/`, all regenerated against the code version above)

- `RE2_Setup_Profile.md`
- `RE2_Time_Distribution.md`
- `RE2_Clustering.md`
- `RE2_Setup_Overlap.md`
- `RE2_Context_Profile.md`
- `RE2_Setup_Transitions.md`
- `RE2_Research_Notes.md` (summary reading of the above - introduces no new calculations)

## Episode semantics

A `SetupEpisode` is a maximal, contiguous run of `detected=True` bars for one setup, built independently per `segment_by_gap` segment (never bridging a gap or an `InsufficientData` position):

- Begins on the first `False`/absent -> `True` activation bar, or on a segment's own first bar if that bar is already `True` (left-censored - see below).
- Continues across consecutive computable `True` bars.
- Ends on the bar BEFORE the run stops - `end_timestamp` is always the last ACTIVE bar, never the first `False` bar.
- Never spans more than one segment.

## Censoring semantics

Every episode carries `termination_reason` (one of `became_false` / `insufficient_data` / `segment_end` / `dataset_end`) and independent `is_left_censored`/`is_right_censored` flags:

- `is_left_censored=True` when the episode's first bar is a segment's own first bar (the true activation could have started earlier, before data coverage begins).
- `is_right_censored=True` for every termination reason except `became_false` (the run's true end is not observed - it was cut off by a data gap, non-computability, or the dataset's own end).
- `RE2_Setup_Profile.md` reports duration statistics for all observed episodes and, separately, only fully-observed (non-censored) episodes. On this dataset the two are statistically indistinguishable to 2 decimal places for every setup - censoring is rare (0-33 left-censored, 2-4 right-censored per setup, out of 1,708-6,331 total episodes) and has no detectable effect on duration distributions at this scale.

## Transition / multi-label semantics

Same-bar ties (two or more setups activating on the identical bar) are represented as a single `ActivationEvent` with a tuple of `activated_setups`, sorted alphabetically for deterministic OUTPUT ordering only - never a claim about which setup "happened first." Episode-level transitions point to the next `ActivationEvent`, never to a single next setup chosen by registry order.

The transition matrix expands each multi-label event into one count per destination setup - `RE2_Setup_Transitions.md` now documents explicitly (added in this freeze patch) that row probabilities are normalized over these EXPANDED DESTINATION LABELS, not over source episodes, and reports the distinguishing counts (non-censored episodes, distinct next events, multi-label next events, expanded destination labels) per row. Same-setup and cross-setup recurrence rates are independently computed and are NOT mutually exclusive - their sum can exceed 100% for a setup whose next events are frequently multi-label (confirmed in the real data, e.g. `liquidity_sweep_with_volume_confirmation`: 48.4% + 97.5% = 145.9%).

## Relationship classification

Every one of the 6 currently-registered setup pairs is classified in `relationships.py` as `SHARED_INPUTS_ONLY` (4 pairs, all sharing `volume_spike` or `displacement`) or `EMPIRICAL` (2 pairs, no shared inputs) - proven from each setup's actual `evaluate()` logic, never inferred from shared inputs alone. **No pair is currently `LOGICALLY_IMPLIED`** - a real, documented finding (none of the 4 setups' detection predicates are a strict subset of another's), not an unfinished analysis. `LOGICALLY_IMPLIED` remains available in the enum for a future setup built directly from `rejection` or `reclaim` (which DO structurally imply `liquidity_sweep` at the fact level, per RE-1's own hierarchy finding).

## Tests

34 new/patched RE-2-specific tests (27 in `test_setup_profiling.py` + 7 in `test_setup_relationships.py`), full suite 1068 passed / 1 skipped, Ruff clean except the one pre-existing, out-of-scope `F401` in `scripts/dev_seed_server.py` (present before RE-1, untouched by RE-2).

## Known limitations

1. **`RunManifest` is imported read-only from RE-1's `atlas.research.statistical_profiling.models`** - a minor package coupling (RE-2 depends on a sibling research package rather than a shared base module). Disclosed as debt, not refactored in this change set per the explicit instruction that RE-1's frozen core is never modified or moved.
2. **An 18-bar `volume_ratio`-null count** appears in every `volume_spike`-dependent setup's computability breakdown, distinct from the already-explained 39-bar ATR-warmup cluster. No root cause is established. Flagged as a targeted, unresolved follow-up required before RE-3 depends on precise `volume_spike` computability counts - it does not block RE-2 or the UI v2 dashboard, since RE-2's own reports already surface the count transparently.
3. **The formal RE-1 certification verdict for this dataset remains REJECTED** (one FAIL: `trend_1m`, a field no RE-2 setup reads) - carried forward unchanged; RE-2's own fitness rests on RE-1's certification report's separate "fit for descriptive Setup Profiling" conclusion, not on the mechanical PASS/WARNING/FAIL rule alone.
4. **No per-instrument tick-size/roll registry** and **no independent contract-roll detection** - both pre-existing, disclosed architectural limitations from before RE-1/RE-2, unchanged.

## Scope discipline maintained

Every RE-2 report and this freeze document describe episode-level Setup Engine structure only: frequency, persistence, time concentration, clustering, pairwise overlap, activation context, and episode-level transitions. No report contains a profitability, expectancy, alpha, forward-return, MFE/MAE, or win-rate claim, and none reads `trend_1m`. `RE2_Research_Notes.md` explicitly separates structural (shared-input) relationships from genuinely empirical ones and states plainly, per this freeze patch, that no causal mechanism is asserted for the 08:00 CT time concentration shared by all four setups.

## Statement

RE-2's six computed reports and research notes have been built, validated, corrected against real report data (the 08:00 CT interpretation, recurrence-rate semantics, and transition-matrix denominator documentation in this freeze patch), and run to completion on the same frozen 97,858-bar, five-file dataset RE-1 certified. No setup definition was changed. RE-1's computation core was never modified or moved.

**RE-2 is complete and frozen. No further RE-2 work is planned unless a correctness defect is discovered in this pipeline. RE-3 has not been started as part of this change set, per explicit instruction. The next sprint is UI v2: Market Intelligence Dashboard.**

# Setup Engine — Setup Inventory

**Status: 4 setups implemented — Sprint 18, Sprint 20, Sprint 21, and Sprint 23B (all 2026-07-19),
the first three steps of the rolling implementation queue from `setup-engine-catalog.md`'s planning
(Sprint 19).** Extends
`setup-engine-architecture.md` (which defines what a setup *is* and how Setup Engine relates to
Rule Engine and the future LLM) into a concrete, per-setup catalog — the same role
`rule-fact-inventory.md` plays for Rule Engine's own facts. See `setup-engine-catalog.md` for the
long-term family taxonomy, candidate setup catalog, capability coverage matrix, and rule-fact
utilization matrix — this document only records what has actually been *built*, not what's planned.

## `displacement_with_volume_confirmation`

- **Sprint**: 18.
- **Family**: `MOMENTUM`.
- **Required facts**: `displacement`, `volume_spike` — both single-bar Rule Engine facts, each
  returning a scalar `bool` with an already-flat evidence dict (no per-reference-level list, unlike
  `rejection`/`liquidity_sweep`/`reclaim`).
- **Required history**: `1` — reads only the current `RuleEngineOutput`; no window needed at the
  Setup Engine layer, since the multi-bar work (`displacement`'s ATR normalization, `volume_spike`'s
  baseline ratio) already happened inside Rule Engine.
- **Definition**: `detected = displacement.value AND volume_spike.value` — a bar whose range
  relative to ATR exceeds `displacement`'s own threshold, and whose volume relative to its own
  baseline exceeds `volume_spike`'s own threshold, on the same bar. The two facts are independent
  by construction: `displacement` reads `high`/`low`/`atr`; `volume_spike` reads `volume_ratio`
  alone — no shared field, no derivation from one to the other in either direction.
- **Insufficient-data propagation**: if `displacement` is `insufficient_data`, its reason is used
  regardless of `volume_spike`'s state; only if `displacement` resolved to a real result is
  `volume_spike` checked next.
- **Severity**: fixed `Severity.NORMAL` for every `detected=True` result. No tiering — calibrating
  a real severity metric from real data is left to a future Sprint, not invented ahead of it.
- **Evidence**: exactly two `SupportingFact` entries, always present regardless of outcome —
  `displacement`'s own `evidence` dict (`range_atr_ratio`, `threshold`) and `volume_spike`'s own
  (`volume_ratio`, `threshold`), passed straight through as `detail` rather than re-keyed field by
  field, so the setup's evidence can never silently drift from `facts.py`'s own field names.
- **Why this was the first setup**: chosen specifically to minimize domain controversy. Its name,
  required facts, deterministic logic, and evidence all describe exactly the same computation —
  proving the Sprint 17B foundation (context construction, evidence, severity, registry,
  serialization, orchestration) against real logic without needing any interpretive claim about
  what a named trading concept "really" means.

## `liquidity_sweep_with_volume_confirmation`

- **Sprint**: 20 — step 1 of the rolling implementation queue from `setup-engine-catalog.md`.
- **Family**: `ICT`.
- **Required facts**: `liquidity_sweep`, `volume_spike`.
- **Required history**: `1` — reads only the current `RuleEngineOutput`; `liquidity_sweep`'s own
  multi-bar window (default 3) was already resolved inside Rule Engine before Setup Engine ever
  sees it.
- **Definition**: `detected = liquidity_sweep.value AND volume_spike.value` — a bar where some bar
  in `liquidity_sweep`'s own window breached a reference level and the current bar's close is back
  on the origin side, confirmed by volume. The two facts are independent by construction:
  `liquidity_sweep` reads high/low across its own window plus the four reference levels;
  `volume_spike` reads `volume_ratio` alone on the current bar.
- **Insufficient-data propagation**: if `liquidity_sweep` is `insufficient_data`, its reason is
  used regardless of `volume_spike`'s state; only if `liquidity_sweep` resolved to a real result is
  `volume_spike` checked next.
- **Severity**: fixed `Severity.NORMAL` for every `detected=True` result, matching Sprint 18 and
  the project-wide decision to defer severity calibration.
- **Evidence**: exactly two `SupportingFact` entries, always present. Unlike
  `displacement_with_volume_confirmation`, `liquidity_sweep`'s own evidence is not already flat —
  `FactResult.evidence["qualifying_levels"]` is a list of per-level records, which cannot be passed
  straight through as `SupportingFact.detail` (bounded to `Mapping[str, int|float|str|bool]`). This
  setup summarizes it instead: `qualifying_level_count` (an int) and `qualifying_levels` (a
  comma-joined string of level names, built via `tuple(sorted(...))` for a stable canonical order —
  applied defensively even though `liquidity_sweep`'s own list is already produced in a fixed order
  internally, so this setup's determinism doesn't silently depend on that staying true).
  `volume_spike`'s evidence is already flat and passed straight through unchanged.

## `sustained_displacement_streak`

- **Sprint**: 21 — step 2 of the rolling implementation queue from `setup-engine-catalog.md`, and
  the first setup requiring `required_history > 1`.
- **Family**: `MOMENTUM`.
- **Required facts**: `displacement` only.
- **Required history**: `2`, derived from `definition.params["min_streak_length"]` via
  `history_param` (the first real use of that mechanism — Sprints 18 and 20 both only ever needed
  1 bar). This is the *minimum* needed to ever detect at all, not a cap: given more history, this
  setup examines all of it and reports the real streak length, unlike Rule Engine's own
  fixed-window facts, which truncate to exactly their configured window. That truncation is correct
  for those facts because their formulas are defined over an exact N-bar window; "how long is the
  current streak" has no such fixed-N definition, so unbounded examination is the correct modeling
  choice here, not a shortcut.
- **Definition**: detects two or more consecutive `RuleEngineOutput` entries, ending at the current
  bar, that each independently satisfy `displacement=True`. Walking backward from the current bar,
  the streak stops at the first bar whose `displacement` is `False` or `insufficient_data` — an
  insufficient bar breaks the streak the same way a `False` bar does, rather than propagating
  insufficiency for the whole setup, since an unconfirmable older bar genuinely cannot corroborate a
  streak. The current bar is treated differently: if `displacement` is `insufficient_data` on
  `context.current` itself, the setup returns `InsufficientData`, since no meaningful streak
  conclusion (including "not detected") can be drawn about right now without knowing what's true
  right now.
- **Insufficient-data conditions**: `len(context.history) < min_streak_length` (not enough bars to
  ever satisfy the minimum); `displacement` is `insufficient_data` on the current bar.
- **Severity**: fixed `Severity.NORMAL` for every `detected=True` result, matching every other
  setup built so far.
- **Evidence**: one `SupportingFact` per bar actually in the streak — a *variable-length* tuple
  (zero entries when the current bar itself doesn't qualify), unlike Sprint 18/20's fixed-two-entry
  shape, which was simply a consequence of those setups checking exactly two facts each time; there
  is no general Setup Engine rule requiring a fixed evidence count. Entries are chronological
  (oldest first, current last), each carrying that bar's own `displacement` evidence plus the
  computed `streak_length` — a scalar, fitting `SupportingFact.detail`'s existing bounded type with
  no Setup Engine model change.

## `vwap_extension_with_volume_confirmation`

- **Sprint**: 23B — step 3 of the rolling implementation queue from `setup-engine-catalog.md`, and
  the first setup under `SetupFamily.CONFLUENCE` (added Sprint 23A, following a dedicated
  classification review — see that document's CONFLUENCE section and `SetupFamily`'s own docstring
  in `atlas/setup_engine/models.py` for the full precedence rule this setup was reviewed against).
- **Family**: `CONFLUENCE`.
- **Required facts**: `vwap_relationship`, `volume_spike`.
- **Required history**: `1` — reads only the current `RuleEngineOutput`; both facts are already
  single-bar Rule Engine facts.
- **Definition**: `detected = vwap_relationship.value != "within_band" AND volume_spike.value is
  True` — a bar where price is extended beyond the configured ATR-normalized band around VWAP
  (either side) and volume is simultaneously elevated. The two facts are independent by
  construction: `vwap_relationship` reads `distance_from_vwap_points`/`atr`; `volume_spike` reads
  `volume_ratio` alone. Reads only each fact's `.value` — never `.evidence` — so this setup never
  re-derives or re-evaluates ATR, VWAP distance, or volume ratio itself; Rule Engine's own
  classification is trusted directly.
- **Deliberately interpretation-neutral**: does not claim continuation, reversal, exhaustion, mean
  reversion, momentum direction, trade entry quality, or probability. This is the reason the setup
  belongs to `CONFLUENCE` rather than `MOMENTUM` or `MEAN_REVERSION` — see the classification review
  in `setup-engine-catalog.md` for the full reasoning already settled before this Sprint began.
- **Insufficient-data propagation**: if `vwap_relationship` is `insufficient_data`, its reason is
  used regardless of `volume_spike`'s state; only if `vwap_relationship` resolved to a real result
  is `volume_spike` checked next — the same deterministic ordering every other
  `_with_volume_confirmation` setup already follows.
- **Severity**: fixed `Severity.NORMAL` for every `detected=True` result, matching every other
  setup built so far.
- **Evidence**: exactly two `SupportingFact` entries, always present. Deliberately does **not**
  copy full Rule Engine evidence into `detail` (unlike `displacement_with_volume_confirmation`'s and
  `liquidity_sweep_with_volume_confirmation`'s flat-evidence passthrough) — only fields derived
  directly from the two fact values: `vwap_relationship_value`/`volume_spike_value` (explicit,
  named copies of each `SupportingFact`'s own `.value`, so `detail` alone is self-describing),
  `is_vwap_extended` (the boolean half of the detection rule), and `extension_side` — present only
  when actually extended, carrying `vwap_relationship.value` verbatim (`"extended_above"` or
  `"extended_below"`; never a third, invented directional label).

## Considered and deferred

A same-bar setup — the current bar's high or low trading beyond a known reference level
(`previous_day_high`, `overnight_high`, `previous_day_low`, `overnight_low`) and the current bar's
own close finishing back on the origin side, with no earlier bar involved — was considered for
Sprint 18. Rule Engine's `rejection` fact already computes this exactly, single-bar, no window
needed. Wrapping `rejection` alone would have been a renamed single-fact wrapper, and a version
composed with `volume_spike` for independent confirmation was set aside in favor of the simpler,
lower-controversy setup above, to keep Sprint 18 focused on proving the foundation rather than
settling a domain-specific classification question. If built later, it gets its own descriptive
name at that time, chosen the same way this document's other entries are — reflecting what it
computes, not a placeholder label.

A second, distinct pattern — an earlier bar's close finishing beyond a reference level, followed by
a later bar's close reclaiming the origin side — is a different, multi-bar structure not addressed
by the setup above. If built, it also gets its own name and Sprint at that time.

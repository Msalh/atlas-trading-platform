# Setup Engine — Long-Term Catalog

**Status: planning approved 2026-07-19 (Sprint 19), persisted here for the first time at Sprint
20's implementation.** This document is the long-term, slow-changing reference for Setup Engine
growth — the family taxonomy, every candidate setup under consideration, coverage analysis, and
missing-fact tracking. It is deliberately separate from `setup-inventory.md`, which records only
what has actually been *built*. Extends `setup-engine-architecture.md`; does not repeat its
reasoning.

## SetupFamily taxonomy

`SetupFamily` (`atlas/setup_engine/models.py`) is a **closed** enum, deliberately — the same
discipline `Timeframe` established: extending it is a real code change requiring justification, not
an arbitrary string. In code today (6 members): `ICT`, `WYCKOFF`, `ORDER_FLOW`,
`AUCTION_MARKET_THEORY`, `MOMENTUM` (Sprint 18), `CONFLUENCE` (Sprint 23A). **`MEAN_REVERSION`
remains catalog-only, not yet in code** — proposed here (Sprint 19) for VWAP-relationship and
reference-level-touch-without-break concepts, structurally the opposite of `MOMENTUM`, but no
setup has ever been implemented under it (`vwap_extension_with_volume_confirmation`, its original
intended first consumer, moved to `CONFLUENCE` — see below; `vwap_extension_with_volume_fade`,
its remaining intended consumer, stays blocked on a missing fact). It gets added to the enum the
same deliberate way `MOMENTUM` and `CONFLUENCE` were, when `vwap_extension_with_volume_fade` (or
another genuine reversion-thesis setup) is actually about to be implemented — not preemptively.
Opening-range/RTH setups deliberately were **not** given their own `SESSION` family — ICT already
treats session-anchored reference levels as core vocabulary, and fragmenting the taxonomy further
wasn't worth it for that one concept.

### CONFLUENCE (added Sprint 23A)

A narrowly-defined neutral family for setups that report the co-occurrence of independent facts
without asserting any directional, continuation, reversal, momentum, or mean-reversion thesis (nor
ICT/Wyckoff/auction-market/order-flow interpretation). The full definition, classification
precedence, and anti-dumping-ground rule are documented permanently in
`SetupFamily`'s own docstring (`atlas/setup_engine/models.py`) — the code is the authoritative,
enforced copy; this section is a pointer to it, not a duplicate to keep in sync by hand.

**Classification precedence, stated here because it governs every future addition to this
catalog, not just `CONFLUENCE` itself**: prefer an existing domain family whenever one fact clearly
defines a setup's primary structure and the others merely confirm it — `CONFLUENCE` is never the
right answer when a real primary structure exists. Use `CONFLUENCE` only when no fact or structure
has legitimate semantic primacy. Two settled examples, not reopened by this addition:
`liquidity_sweep_with_volume_confirmation` stays `ICT` (`liquidity_sweep` is the primary
structure, `volume_spike` only confirms it); `displacement_with_volume_confirmation` stays
`MOMENTUM` (`displacement` is the primary structure, `volume_spike` only confirms it). By the same
reasoning, `vwap_extension_with_volume_confirmation` belongs to `CONFLUENCE`: VWAP extension and a
volume spike are two independently-computed conditions with neither having primacy over the
other, and the setup's own definition affirmatively asserts no thesis about what their
co-occurrence means.

**Anti-dumping-ground rule**: `CONFLUENCE` must never become the default answer for "this setup is
hard to classify." A setup that resists classification is a signal to re-examine it for a primary
structure that hasn't been identified yet, not evidence it belongs here. Every future `CONFLUENCE`
candidate must satisfy all of: (1) composes 2+ independently-computed Rule Engine facts, (2) its
`detected` result means only that those conditions coexist, (3) it does not assert any of the
interpretations listed above, (4) no existing family truthfully describes its primary structure.

## Capability taxonomy — explicitly open, unlike SetupFamily

Capabilities (`Trend`, `Momentum`, `Liquidity`, `Volume`, `VWAP`, `Session`, `Market Structure`,
`Mean Reversion`, `Multi-timeframe`, `Volatility`, `Order Flow / Auction Profile`) are a
**planning/documentation lens only** — not implemented in code, not a registry, no validation. They
exist purely to answer a different question than `SetupFamily` does: not "what kind of setup is
this" but "what does the setup library actually cover, and where is it concentrated." This list
should evolve freely as new cross-cutting concerns become visible — `Order Flow / Auction Profile`
was added mid-analysis specifically because the utilization matrix below needed it. Future
additions or removals don't need a deliberate-extension process the way `SetupFamily` does.

## Candidate setup catalog, by family

"Dependencies" is **None** for every entry unless stated — checked explicitly against the standing
"no setup-on-setup dependencies" rule; none needed one.

### ICT

| Setup | Purpose | Required facts | History | Complexity | Priority |
|---|---|---|---|---|---|
| `liquidity_sweep_with_volume_confirmation` | *(implemented, Sprint 20)* | `liquidity_sweep`, `volume_spike` | 1 | Low | Done |
| `reclaim_with_volume_confirmation` | Close-based break-then-reclaim of a level, confirmed by volume | `reclaim`, `volume_spike` | 1 | Low | High |
| `rejection_with_volume_confirmation` | Same-bar wick-and-reclose against a reference level, confirmed by volume | `rejection`, `volume_spike` | 1 | Low — its qualifying-level aggregation (`qualifying_level_count` + sorted `reference_level` names) is identical in shape to the already-shipped `liquidity_sweep_with_volume_confirmation` pattern; corrected from an earlier "Medium" rating that assumed a harder aggregation than the fact's evidence actually requires | High |
| `trend_aligned_liquidity_sweep` | A sweep whose reclaim direction agrees with `trend_5m` | `liquidity_sweep`, `trend_5m` | 20 | Medium — needs its own directional-alignment design pass | Medium |
| `fair_value_gap_with_displacement` | 3-candle OHLC imbalance confirmed by high displacement | new fact `fair_value_gap` + `displacement` | 2–3 | Medium | Medium — blocked on missing fact |
| `opening_range_reference` | Price behavior relative to the RTH session open | new fact `rth_session_context` + `displacement`/`volume_spike` | small | Medium | Low-Medium — blocked on missing fact |
| `multi_level_liquidity_sweep` | `liquidity_sweep` qualifying on 2+ levels at once | `liquidity_sweep` only, thresholded on its own qualifying-level count | 1 | Low, but a real edge case worth naming: `detected` is a stricter threshold on one fact's internal evidence, not an identity passthrough | Low |
| `order_block_reversal` | ICT "order block" (last opposing candle before a strong displacement move) | undesigned | n/a | High | **Defer** — definitions vary meaningfully across ICT practitioners |

#### Refinement/supertype coexistence rule (Sprint 24A)

`liquidity_sweep`, `rejection`, and `reclaim` are **not three independent peer ICT primitives** —
the Sprint 24A Rule Fact Independence Audit found `rejection` is an unconditional predicate
refinement of `liquidity_sweep` (whenever both are computable), and `reclaim` is a predicate
refinement of `liquidity_sweep` under the current matched default window configuration (both
`window=3`); `rejection` and `reclaim` remain independent of each other. See
`docs/market_engine/rule-fact-inventory.md`, "Fact hierarchy within this family," for the full
proof — this section states only the resulting catalog policy, not the proof itself.

**Permanent rule**: a refinement-based setup (`rejection_with_volume_confirmation`,
`reclaim_with_volume_confirmation`) and a supertype-based setup
(`liquidity_sweep_with_volume_confirmation`) may both exist in the catalog, both be registered, and
both fire and be reported independently on the same bar — Setup Engine itself must never suppress,
merge, or deduplicate them; this is Rule Engine's and Setup Engine's ordinary independent-evaluation
behavior and stays that way. However, any downstream consumer that aggregates, scores, weights, or
narrates setup outcomes must treat a refinement firing alongside its supertype as **one structural
evidence family, not two independent confirmations** — whenever the refinement fires, the supertype
is structurally guaranteed to fire too (given the same confirming fact), so counting both toward
confidence or corroboration double-counts a single event.

### MOMENTUM

| Setup | Purpose | Required facts | History | Complexity | Priority |
|---|---|---|---|---|---|
| `displacement_with_volume_confirmation` | *(implemented, Sprint 18)* | `displacement`, `volume_spike` | 1 | — | Done |
| `sustained_displacement_streak` | *(implemented, Sprint 21)* — 2+ consecutive bars each independently showing `displacement=True` | `displacement` | 2 | Medium — the first setup needing `required_history > 1` | Done |
| `trend_aligned_displacement` | High-displacement bar in the direction `trend_5m` favors | `displacement`, `trend_5m` | 20 | Blocked — `displacement` exposes magnitude only, no directional sign | Blocked |

### CONFLUENCE

| Setup | Purpose | Required facts | History | Complexity | Priority |
|---|---|---|---|---|---|
| `vwap_extension_with_volume_confirmation` | *(implemented, Sprint 23B)* — `vwap_relationship` is extended (either side) on the same bar `volume_spike` fires — `detected = (vwap_relationship.value != "within_band") AND volume_spike.value is True`. Deliberately asserts no reversion/continuation thesis: whether an extension-plus-volume-spike co-occurrence means climactic exhaustion or strong continuation is genuinely ambiguous, and Setup Engine reports structure, not interpretation. Moved here from `MEAN_REVERSION` (Sprint 23A) — see the classification review below. | `vwap_relationship` *(implemented, Sprint 22B)*, `volume_spike` | 1 | Low — same `_with_volume_confirmation` shape as the setups already built | Done |

### MEAN_REVERSION

**Corrected Sprint 22A/22B** — this family's original entry, `vwap_reversion_with_volume_fade`,
had an internal inconsistency: its purpose text claimed "volume declining," but its required facts
named `volume_spike`, which measures *elevated* volume — the opposite. There is no fact, built or
previously proposed, that measures declining/fading volume over a window. Split into two correctly
scoped entries; the confirmation half moved on to `CONFLUENCE` (Sprint 23A, see above and the
review below) once that contradiction turned out to run deeper than a naming fix.

| Setup | Purpose | Required facts | History | Complexity | Priority |
|---|---|---|---|---|---|
| `vwap_extension_with_volume_fade` | The original mean-reversion-via-exhaustion thesis, preserved under a correct name: `vwap_relationship` extended, with volume *declining* rather than spiking. Genuinely asserts a reversion thesis — `MEAN_REVERSION` remains the truthful family for this one. | `vwap_relationship` *(implemented, Sprint 22B)* + a new windowed volume-trend fact | 1–several | Medium | **Defer** — blocked on a new fact; explicitly not approximated with `volume_spike` (see `reclaim`'s own borderline-dead history for what happens when a fact is asked to serve a purpose it wasn't built for) |
| `reference_level_touch_without_break` | Price approaches a known level closely without sweeping or rejecting it | new fact `liquidity_proximity` + `liquidity_sweep` (False) | 1 | Medium | Medium — blocked on missing fact |

**Note on this candidate's required facts (Sprint 24A)**: an earlier version of this row also
required `rejection` (False) alongside `liquidity_sweep` (False), on the assumption that "no sweep
and no rejection" was a stronger, more specific condition than "no sweep" alone. The Rule Fact
Independence Audit found this redundant: `rejection` is an unconditional predicate refinement of
`liquidity_sweep` (`rejection=True` always implies `liquidity_sweep=True` when both are
computable), so by contraposition `liquidity_sweep=False` already guarantees `rejection=False` —
checking `rejection` again adds no additional filtering, only the appearance of a stronger
condition. `liquidity_proximity`'s own "close to a level" test remains this setup's actual, genuine
distinguishing condition once built; it is not weakened by dropping the redundant clause.

#### SetupFamily classification review — `vwap_extension_with_volume_confirmation` (resolved Sprint 23A)

**Resolution: `SetupFamily.CONFLUENCE` added (Sprint 23A); setup reclassified from `MEAN_REVERSION`
to `CONFLUENCE` above.** Retained below as the record of the analysis that produced that decision,
per this project's standing "mark resolved, don't delete" rule. Raised because the setup's own
definition and its catalog family contradicted each other:
`vwap_extension_with_volume_confirmation` explicitly asserts no reversion/continuation thesis, but
`MEAN_REVERSION` as a family name asserts exactly that. Working through each question in turn:

- **Is `MEAN_REVERSION` still truthful for this setup?** No. The family name itself is a claim
  ("this setup is about fading an extension"); the setup's own text explicitly disclaims that
  claim. Leaving it there isn't a stretch, it's a direct contradiction — the same category of
  defect the Documentation Maintenance Rule now exists to catch, just inside a table cell instead
  of across two documents.
- **Would `MOMENTUM` be equally misleading?** Yes, for the mirror-image reason. `MOMENTUM`
  (`displacement_with_volume_confirmation`, `sustained_displacement_streak`) asserts a
  continuation/expansion thesis. Moving this setup there would trade one smuggled interpretation
  for its opposite, not remove the problem.
- **Does the closed `SetupFamily` enum lack a neutral structural/co-occurrence family?** Yes,
  confirmed by inspection. All six current members assert an interpretation of some kind: `ICT`,
  `WYCKOFF`, `AUCTION_MARKET_THEORY` are named trading philosophies; `MOMENTUM` and
  `MEAN_REVERSION` are directional-technique categories (continuation vs. reversion);
  `ORDER_FLOW` is empty but would, when populated, describe order-flow-specific interpretation.
  None of the six describe "these conditions co-occurred, no directional claim" — which is
  precisely what this setup's own design says it does.
- **Could the setup definition be changed instead, without smuggling in interpretation?** Not
  without changing what it actually computes. The only way to make `MEAN_REVERSION` or `MOMENTUM`
  honestly fit would be to bias the setup toward one interpretation (e.g. restrict it to only
  `extended_below` + volume spike, framed as an exhaustion signal) — which would be choosing the
  setup's logic to match a family label, backwards from how every other setup in this catalog was
  designed, and a direct reintroduction of the interpretive-commitment risk the whole
  `vwap_extension_with_volume_confirmation` design was built to avoid in the first place.
- **Recommendation (accepted, implemented Sprint 23A): add a new, genuinely neutral family**
  rather than force-fitting an existing one. Name chosen: **`CONFLUENCE`** — a recognized
  technical-analysis term for "multiple conditions lining up," with no inherent directional claim,
  unlike `STRUCTURAL` (too vague — every Setup Engine output is structural by the architecture's
  own definition) or `CO_OCCURRENCE` (accurate but reads as a description of the mechanism rather
  than a family a trader would recognize, unlike `ICT`/`WYCKOFF`/`AUCTION_MARKET_THEORY`/
  `MOMENTUM`/`MEAN_REVERSION`, which all name real, in-use vocabulary). A closed-enum extension,
  the same kind `MOMENTUM` itself already was (Sprint 18) — not a redesign of the taxonomy, one
  deliberate addition to it.
- **Alternatives considered and rejected**: leaving it under `MEAN_REVERSION` as-is (status quo) —
  rejected, it's the defect being raised, not a resolution of it; moving it to `MOMENTUM` —
  rejected above, equally misleading; broadening `MEAN_REVERSION`'s own definition to cover
  neutral confluence too — rejected, it would dilute the family's meaning for genuinely
  reversion-thesis setups like `vwap_extension_with_volume_fade`, which correctly keeps
  `MEAN_REVERSION` under this same review's own reasoning.
- **Should Sprint 23 pause for this? Yes, and it did.** `SetupFamily` is closed by deliberate
  design specifically so a new member requires a disclosed decision, not a default. Implementing
  `vwap_extension_with_volume_confirmation` under a family its own text contradicts would have
  shipped a documentation defect in code, not just in prose — worse than the two documentation
  drifts that prompted the Documentation Maintenance Rule two Sprints ago, since this one would
  have been compiled into `SetupDefinition.family` rather than sitting in a markdown table. Sprint
  23 split into 23A (this taxonomy amendment, `SetupFamily.CONFLUENCE` added, no setup
  implementation) and a later Sprint for the setup itself, once resolved.

### WYCKOFF

All real Wyckoff setups depend on a consolidation-range fact that doesn't exist. Listed for
completeness, not near-term work:

| Setup | Purpose | Blocker | Priority |
|---|---|---|---|
| `spring_with_volume_climax` | Range-low sweep with climactic volume, then reversal | new `range_context` fact + `volume_spike` | **Defer** |
| `upthrust_with_volume_climax` | Symmetric, range-high | Same | **Defer** |
| `test_of_support_low_volume` | Revisit of a prior low on declining volume | new `range_context` fact + a new windowed volume-trend fact — **the same fact `vwap_extension_with_volume_fade` (MEAN_REVERSION, above) is blocked on**, not a coincidence; building it unblocks both setups at once | **Defer** |

### AUCTION_MARKET_THEORY

Genuine value-area/POC/TPO concepts need volume distributed across price levels — data this system
has never ingested. Not buildable:

| Setup | Purpose | Blocker | Priority |
|---|---|---|---|
| `value_area_rejection` | Price rejects the edge of the session's value area | No volume-at-price ingestion | **Defer — ingestion-blocked** |
| `poc_migration_continuation` | Point-of-control shift confirms trend direction | Same | **Defer — ingestion-blocked** |

A VWAP-based approximation of "value area center" belongs to `MEAN_REVERSION`
(`vwap_extension_with_volume_confirmation`/`vwap_extension_with_volume_fade` above), not this
family — deliberately not proposed as a fake AMT setup.

### ORDER_FLOW

No candidates proposed. Named only so the roadmap shows what it would eventually hold:
`delta_divergence`, `absorption_at_level`, `footprint_imbalance_reversal`. Stays empty until real
order-flow ingestion exists.

## Missing Rule Engine facts blocking future setups

Ranked by cost-to-build vs. how much they unblock:

1. ~~**`vwap_relationship`** — thresholds the already-raw `distance_from_vwap_points`.~~ —
   **implemented, Sprint 22B** (`atlas.rule_engine.facts.evaluate_vwap_relationship`). Unblocked
   `vwap_extension_with_volume_confirmation` fully — **implemented, Sprint 23B**; unblocks
   `vwap_extension_with_volume_fade` only partially (still needs item 2 below).
2. **Windowed volume trend** — needed for `vwap_extension_with_volume_fade` (MEAN_REVERSION) *and*
   Wyckoff's `test_of_support_low_volume` — the same fact, two waiting consumers, not a coincidence.
3. **`liquidity_proximity`** — wraps the already-raw `nearest_liquidity_level`/`nearest_liquidity_type`/
   `distance_to_liquidity_ticks`. Unblocks "near a key level" as an independent condition.
4. **`rth_session_context`** — wraps the already-raw `is_rth`/`session_name`/`rth_open`. Unblocks
   ICT opening-range setups.
5. **Reference-level status facts** (`overnight_high_status`/`overnight_low_status`/
   `previous_day_high_status`/`previous_day_low_status`, already named in `rule-fact-inventory.md`)
   — would be the **first stateful, session-scoped** Rule Engine facts; every fact today is
   memoryless. Deserves its own planning Sprint before implementation, not folded into a setup
   Sprint. As of Sprint 22B, zero concrete candidate setup names them yet, despite this identified
   need — a real gap between "identified" and "designed."
6. **Directional sign on `displacement`** — currently magnitude-only. Blocks `trend_aligned_displacement`.
7. **`fair_value_gap`** — a new 3-candle OHLC-geometry fact. No new ingestion needed, low
   domain-controversy (mechanical test, unlike `order_block`'s disputed definition).
8. **Range/consolidation detection** (`range_context`) — blocks nearly all of Wyckoff. Genuinely
   complex; likely deserves its own planning Sprint, the way Rule Engine's windowed facts got
   Sprint 13.
9. **5m→15m / 5m→1h aggregation** — already known-blocked in `rule-fact-inventory.md`; unblocks
   `trend_15m`/`trend_1h`, which in turn unblock multi-timeframe confirmation setups not yet listed.

## Capability Coverage Matrix

`*` = tag depends on an undecided confirming fact choice. `†` = conceptual only — no real fact
exists yet, tag reflects intended capability once designed, not a verified computation.

| Setup | Family | Trend | Momentum | Liquidity | Volume | VWAP | Session | Mkt Structure | Mean Reversion | Multi-TF | Volatility | Order Flow |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `displacement_with_volume_confirmation` | Momentum | | ✓ | | ✓ | | | | | | ✓ | |
| `liquidity_sweep_with_volume_confirmation` | ICT | | | ✓ | ✓ | | | ✓ | ✓ | | | |
| `reclaim_with_volume_confirmation` | ICT | | | ✓ | ✓ | | | ✓ | ✓ | | | |
| `rejection_with_volume_confirmation` | ICT | | | ✓ | ✓ | | | ✓ | ✓ | | | |
| `trend_aligned_liquidity_sweep` | ICT | ✓ | | ✓ | | | | ✓ | | | | |
| `fair_value_gap_with_displacement` | ICT | | ✓ | | | | | ✓ | | | ✓ | |
| `opening_range_reference` | ICT | | | | ✓* | | ✓ | | | | | |
| `multi_level_liquidity_sweep` | ICT | | | ✓ | | | | ✓ | ✓ | | | |
| `order_block_reversal` *(deferred)* | ICT | | ✓† | | | | | ✓† | | | | |
| `sustained_displacement_streak` | Momentum | | ✓ | | | | | | | | ✓ | |
| `trend_aligned_displacement` *(blocked)* | Momentum | ✓ | ✓ | | | | | | | | ✓ | |
| `vwap_extension_with_volume_confirmation` | Confluence | | | | ✓ | ✓ | | | | | | |
| `vwap_extension_with_volume_fade` *(deferred)* | Mean Reversion | | | | ✓† | ✓ | | | ✓ | | | |
| `reference_level_touch_without_break` | Mean Reversion | | | ✓ | | | | | ✓ | | | |
| `spring_with_volume_climax` *(deferred)* | Wyckoff | | | | ✓ | | | ✓† | ✓† | | ✓† | |
| `upthrust_with_volume_climax` *(deferred)* | Wyckoff | | | | ✓ | | | ✓† | ✓† | | ✓† | |
| `test_of_support_low_volume` *(deferred)* | Wyckoff | | | | ✓† | | | ✓† | | | | |
| `value_area_rejection` *(ingestion-blocked)* | AMT | | | | | | | ✓† | ✓† | | | ✓† |
| `poc_migration_continuation` *(ingestion-blocked)* | AMT | ✓† | ✓† | | | | | ✓† | | | | ✓† |
| `delta_divergence`/`absorption_at_level`/`footprint_imbalance_reversal` *(ingestion-blocked)* | Order Flow | | | | | | | | | | | ✓ |

**Gap analysis**: the concretely-designed catalog is heavily concentrated in **Liquidity** (6 of 9
near-term setups) and **Market Structure** (7 of 9), both dominated by ICT — the exact concentration
risk this exercise was meant to catch. **Multi-timeframe has zero coverage**, fully blocked on the
known `trend_15m`/`trend_1h` aggregation gap. **Session still has one setup, blocked** on an
undesigned fact; **VWAP now has two**, one implemented (`vwap_extension_with_volume_confirmation`,
Sprint 23B) and one still blocked (`vwap_extension_with_volume_fade`). **Volatility coverage is
entirely inherited from one fact** (`displacement`) —
if its definition needs rework, the whole column collapses with it. **Volume is broad but never
primary** — always the confirming signal, never the setup's own reason for existing. **Mean
Reversion is present but under-labeled** — sweep/reclaim/rejection setups are structurally
reversion patterns (tagged accordingly above) even though the dedicated `MEAN_REVERSION` family
itself is thin and blocked.

## Rule Fact Utilization Matrix

"Confirmed" = named by a concretely-designed, near-term candidate. "Conceptual" = named only by a
deferred/undesigned setup.

| Fact | Status | Confirmed consumers | Total | Classification |
|---|---|---|---|---|
| `volume_spike` | Implemented | 5 confirmed (`displacement_with_volume_confirmation`, `liquidity_sweep_with_volume_confirmation`, `reclaim_with_volume_confirmation`, `rejection_with_volume_confirmation`, `vwap_extension_with_volume_confirmation`) + 2 conceptual | 7–8 | **Broadly reused** |
| `displacement` | Implemented | 4 (`displacement_with_volume_confirmation`, `fair_value_gap_with_displacement`, `sustained_displacement_streak`, `trend_aligned_displacement`) | 4–5 | **Broadly reused** |
| `liquidity_sweep` | Implemented | 4 (`liquidity_sweep_with_volume_confirmation`, `trend_aligned_liquidity_sweep`, `multi_level_liquidity_sweep`, `reference_level_touch_without_break`) | 4 | **Broadly reused** |
| `rejection` | Implemented | 1 (`rejection_with_volume_confirmation`) — `reference_level_touch_without_break` no longer counts (Sprint 24A: its `rejection=False` clause was dropped as redundant with `liquidity_sweep=False`, see the MEAN_REVERSION table note above) | 1 | Lightly used |
| `trend_5m` | Implemented | 2 (`trend_aligned_liquidity_sweep`, `trend_aligned_displacement`), neither built | 2 | Lightly used |
| `reclaim` | Implemented | 1 (`reclaim_with_volume_confirmation`) | 1 | Lightly used — **borderline dead; see note** |
| `vwap_relationship` | **Implemented, Sprint 22B** | 2 (`vwap_extension_with_volume_confirmation`, **implemented, Sprint 23B**; `vwap_extension_with_volume_fade`, designed but deferred, blocked on a missing fact) | 2 | Lightly used |
| `liquidity_proximity` | Proposed | 1 (prospective) | 1 | Lightly used (prospective) |
| `rth_session_context` | Proposed | 1 (prospective) | 1 | Lightly used (prospective) |
| `fair_value_gap` | Proposed | 1 (prospective) | 1 | Lightly used (prospective) |
| `range_context` | Proposed | 3, all conceptual | 3 | Broadly reused (prospective, entirely conceptual) |
| Windowed volume trend | Proposed | 2 — `vwap_extension_with_volume_fade` (designed, deferred) and `test_of_support_low_volume` (conceptual) | 2 | Lightly used (prospective) — shared by two families, worth building once either is prioritized |
| `trend_1m` | Blocked (hard) | — | 0 | Unused — expected, ingestion-blocked |
| `trend_15m` | Blocked (soft) | — | 0 | Unused — expected, aggregation-blocked |
| `trend_1h` | Blocked (soft) | — | 0 | Unused — expected, aggregation-blocked |
| Reference-level status facts (×4) | Undesigned | — | 0 | Unused — **not expected: identified need, no drafted consumer** |

**Note on `reclaim` and `rejection` (Sprint 24A: Rule Fact Independence Audit)**: `reclaim`'s only
consumer, `reclaim_with_volume_confirmation`, was deliberately not implemented in Sprint 20 in
favor of `liquidity_sweep_with_volume_confirmation` — meaning `reclaim` currently drives zero
*built* setups. The audit confirmed and formalized the earlier finding that `reclaim=True` implies
`liquidity_sweep=True`, but under the current matched default window configuration only
(config-contingent — see `docs/market_engine/rule-fact-inventory.md`, "Fact hierarchy within this
family"). The audit also found a **stronger, unconditional** version of the same relationship for
`rejection`: `rejection=True` implies `liquidity_sweep=True` whenever both facts are computable,
regardless of window configuration — meaning `rejection_with_volume_confirmation`, if built, would
also always co-fire alongside `liquidity_sweep_with_volume_confirmation` on the same bar, not just
usually. Neither finding blocks either setup from existing (see the "Refinement/supertype
coexistence rule" under the ICT table above) — both `reclaim` and `rejection` remain genuine
candidates for future reconsideration, surfaced here, not acted on.

**Over-centralized facts**: `volume_spike`, `displacement`, `liquidity_sweep` anchor almost the
entire near-term catalog — the three facts most worth prioritizing for real calibration once
production data exists, precisely because of how much leans on them.

## Rolling implementation roadmap

This section is **intentionally short-lived** — it should be re-derived after each completed
Sprint against the tables above, not extended into a long fixed schedule. See `setup-inventory.md`
for what's actually been built.

**As of Sprint 23B**: all five steps of the original queue are complete. Steps 1–3
(`liquidity_sweep_with_volume_confirmation`, `sustained_displacement_streak`, `vwap_relationship`)
landed across Sprints 20–22B. Step 4 went through two corrections before implementation: the
queue's original step-4 entry, `vwap_reversion_with_volume_fade`, named `volume_spike` (elevated
volume) while its purpose text claimed declining volume (caught pre-implementation, split into
`vwap_extension_with_volume_confirmation` and the correctly-deferred
`vwap_extension_with_volume_fade`); the confirmation half then turned out to contradict its own
cataloged family (`MEAN_REVERSION` asserts a reversion thesis the setup's own definition
explicitly disclaims), resolved by adding `SetupFamily.CONFLUENCE` (Sprint 23A) and reclassifying
it before — not after — implementation. **`vwap_extension_with_volume_confirmation` is now
implemented (Sprint 23B)** — the first `CONFLUENCE`-family setup, registered, tested, and
documented. Step 5, "re-evaluate," is what comes next:

This section's own next action is to be **re-derived from the tables above**, not extended into a
fixed list here — see `roadmap.md`'s "Next planning point" for the currently-open decision (which
setup or fact comes next has not been chosen yet, deliberately, per the rolling-queue's own
design).

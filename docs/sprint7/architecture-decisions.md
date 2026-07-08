# Sprint 7 - Architecture Decisions

## 1. Structured output first, narrative second - enforced by construction
`atlas/intelligence.py::compute_intelligence_snapshot` computes the confidence score,
expected R, historical win rate, and the measurable factors behind them **before**
`atlas/ai.py::run_entry_score` ever calls Claude. Claude is handed those already-computed
numbers via `build_intelligence_prompt` and is explicitly instructed not to invent or
override the score - its only job is a 2-3 sentence explanation of numbers it didn't
produce. This is the literal architectural difference from Sprint 6's entry scoring, where
Claude's raw text (`SCORE:`/`LABEL:`/`REASONING:`) *was* the score, defensively parsed by
`atlas/ai.py::parse_entry_score`. That function and the old `SCORE:`/`LABEL:` prompt format
are removed entirely - there is nothing left to parse out of Claude's response for entry
scoring, its raw text is stored as-is.

## 2. Historical retrieval and statistics, explicitly not machine learning
Per your instruction ("Do not introduce ML training"), `atlas/intelligence.py` has no
training step, no fitted parameters, and no model file. `find_similar_trades` is a
hand-designed distance measure over three named fields (`regime_slope_pct`,
`ema_distance_atr`, `sweep_age_bars`), each normalized by a hand-picked typical scale - not
a learned embedding. `compute_confidence` is a fixed, documented point rubric (sample size:
0-4 points, historical win rate: 0-4 points, positive expectancy: 0-2 points, capped at 10) -
not a fitted/learned function. Every threshold in the module is a constant you can read and
change directly in the source, not a coefficient discovered from data.

## 3. Similarity is a hard categorical filter, then a continuous ranking
"Similar" first means same `direction` and same `setup_tag` among **closed** trades only (an
open position has no outcome to learn from yet) - these are hard filters, not soft signals,
because changing either fundamentally changes what kind of trade it is. Within that filtered
set, trades are ranked by closeness on the continuous factors and the closest `max_results`
(default 20) are kept. `find_similar_trades` also excludes the entry's own
`correlation_id`, so scoring a trade never counts itself as historical evidence for itself.

## 4. Zero historical precedent skips Claude entirely, not just the score
When `similar_trade_count == 0`, `run_entry_score` never calls `analyze_with_claude` at all -
there is nothing yet for it to explain, and calling it anyway would just produce prose about
nothing. The stored `ai_notes` row instead gets a static, honest message
(`score=None, score_label="Insufficient History"`) and the `ai.entry_scored` event still
publishes normally (`ok: true`) - a lack of history is not treated as a failure. Note that
a *thin* sample (1-3 similar trades) is different: a score **is** computed and Claude **is**
called, but `compute_confidence` still forces the label to `"Insufficient History"` even
though a numeric score exists, so the UI can distinguish "a real but shaky signal" from "no
signal at all."

## 5. A Claude failure no longer nulls out the score
Because the score is computed before Claude is ever invoked, a failed or unconfigured Claude
call (`ANTHROPIC_API_KEY not configured`, a timeout, any exception) only means the narrative
explanation is missing - `score`, `score_label`, `expected_r`, `historical_win_rate_pct`, and
`factors` are still written to the `ai_notes` row from the already-computed
`IntelligenceSnapshot`. This is the opposite of Sprint 6's behavior, where a Claude failure
meant the entire entry_score row had `score=None` because the score itself came from parsing
Claude's response. The frontend timeline reflects this: an `entry_score` event with an
`error` can still show a real `N/10` score right next to "Narrative unavailable — \<error\>".

## 6. `ai_notes` gained four columns, only meaningful for `entry_score`
Migration `0004_ai_intelligence_fields.sql` adds `expected_r`, `historical_win_rate_pct`,
`similar_trade_count` (all nullable), and `factors_json` (a JSON-encoded list, same TEXT-column
pattern as `trades.raw_entry_payload`, decoded at the repository boundary via
`postgres.py::_decode_ai_note` so callers always see a real Python list). These four are
always `NULL` for `post_trade_review`/`daily_report`/`weekly_report` rows - post-trade review
and reports are unchanged from Sprint 6 and don't go through `atlas/intelligence.py` at all.
`TradeRepository.add_ai_note` takes them as optional keyword-only parameters with `None`
defaults, so the interface change is additive and doesn't touch any Sprint 4-6 call site.

## 7. `atlas/intelligence.py` reuses `atlas/analytics.py::compute_summary`, not a parallel aggregation
The "similar setup statistics" (historical win rate, expected R = average R-multiple) are
computed by calling `compute_summary` on the similarity-filtered trade subset - the exact
same function that powers the `/analytics` page's summary cards. A similar-trades summary
and the Analytics page's summary can never disagree about what "win rate" or "expectancy"
means, because they're the same function call on different (filtered) input. This mirrors
Sprint 6's decision to reuse `compute_summary`/`compute_breakdown` for report generation
rather than inventing a second aggregation path.

## 8. On-demand intelligence is a distinct endpoint, not a repeat of entry-time scoring
`GET /api/v1/ai/intelligence/{correlation_id}` recomputes a fresh `IntelligenceSnapshot`
synchronously on every call - no Claude call, nothing persisted, works for any trade (open or
closed), not just the one scored at entry time. This is deliberately different in kind from
the stored `entry_score` `ai_notes` row, which is a one-time snapshot taken when the trade
was first received: history keeps accumulating after that, so "what would we compute right
now" and "what did we compute back then" are genuinely different, useful answers. There is no
"re-score this trade" REST action that also calls Claude again - only the read-only,
zero-cost recomputation, consistent with Sprint 6's decision not to expose a manual
"score this trade" trigger over REST.

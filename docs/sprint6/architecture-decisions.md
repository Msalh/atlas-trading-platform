# Sprint 6 - Architecture Decisions

## 1. "AI must run async/background only" is enforced by construction, not convention
`atlas/api/v1/webhook.py` never awaits anything in `atlas/ai.py` directly - it only ever
does `background_tasks.add_task(run_entry_score, ...)` (on entry) and
`background_tasks.add_task(run_post_trade_review, ...)` (on a matched exit). Both are
scheduled *after* the response-critical work (PickMyTrade forward, DB write, event
publish) is already done. Same for the new REST trigger: `POST /api/v1/ai/reports/{period}`
schedules `run_report_generation` as a background task and returns `202 Accepted`
immediately - it never awaits the Claude call itself, even though report generation has
no webhook/order-execution involvement at all. This is the same discipline Sprint 1
established for the original entry-analysis background task, now applied consistently
to every AI-triggering code path in the system, not just the one on the webhook route.

## 2. `ai_notes` table replaces the old single-slot `llm_model`/`llm_analysis`/`llm_error` columns
The original Sprint 0-5 schema could only hold one AI note per trade - fine for a single
entry-time comment, not enough once a trade also gets a post-trade review, and reports
aren't tied to any one trade at all. `ai_notes` (migration `0003_ai_notes.sql`) is one row
per AI pass: `note_type` distinguishes entry_score / post_trade_review / daily_report /
weekly_report, and `trade_correlation_id` is nullable (NULL for report types, which
summarize many trades). This is exactly the `ai_analyses` table the original V2
architecture sketch anticipated - built now because Sprint 6 is the first sprint with a
concrete second and third use ("a trade can get multiple AI passes"), not built earlier as
speculation.

The old `trades.llm_model`/`llm_analysis`/`llm_error` columns are left in place, untouched,
purely as a read-only record of pre-Sprint-6 entries - nothing new is ever written there
(`TradeRepository.update_ai_analysis` was removed from the interface and both
implementations; `atlas/api/v1/trades.py::build_timeline` still reads them as a fallback
only when a trade has no real `ai_notes` rows, so old data doesn't disappear from the UI).

## 3. One low-level Claude function, three prompt builders, parsing kept separate
`atlas/services/claude.py::analyze_with_claude` now takes a finished prompt string and
returns raw `(text, error)` - it has no opinion about what kind of analysis it's for. Three
prompt builders (`build_entry_score_prompt`, `build_post_trade_review_prompt`,
`build_report_prompt`) live in the same module. Parsing Claude's response into something
structured (`atlas/ai.py::parse_entry_score`) is a separate function in a separate module -
"talk to Claude" and "make sense of what Claude said" are independently testable, and a
parsing bug can never look like an API bug or vice versa.

## 4. Entry score parsing is defensive, not a strict contract with the model
The prompt asks Claude to respond in an exact `SCORE:`/`LABEL:`/`REASONING:` format, but
`parse_entry_score` never assumes it complied: a missing or out-of-range `SCORE:` just
means `score = None`; a missing `REASONING:` marker falls back to using the full response
text as the reasoning, so a parsing miss never loses the actual content, only the
structure around it. `content` (what actually gets stored and shown) is never fabricated -
it's either Claude's real reasoning text or nothing.

## 5. Report generation windows are simple, stated plainly
"Daily" = trades closed since UTC midnight today; "weekly" = trades closed in the last 7
days. No trading-session-boundary awareness, no timezone configuration - the same kind of
simplification Sprint 2's `stats.py` and Sprint 5's `analytics.py` already made and
documented for "today," applied consistently here rather than inventing a different
convention for reports specifically.

## 6. Report generation reuses Sprint 5's analytics functions unmodified
`run_report_generation` filters the trade list to the report's date window in Python, then
calls the *exact same* `compute_summary`/`compute_breakdown` from `atlas/analytics.py` that
power the `/analytics` page - not a parallel aggregation path. A report's numbers and the
Analytics page's numbers can't drift apart from each other because they're the same
function calls on the same (differently-filtered) input.

## 7. REST surface: four endpoints, matching how the frontend actually consumes this
`GET /api/v1/ai/notes` (global feed, optionally filtered - powers both the trade-detail
timeline via the repository call in `trades.py` and the standalone AI Notes Timeline),
`GET /api/v1/ai/reports` + `POST /api/v1/ai/reports/{period}` (list / trigger, matching the
Reports panel's two concerns), all under `/api/v1/ai/*`. Entry scoring and post-trade
review are not directly triggerable via REST - they only ever happen automatically from
the webhook, by design (there's no "score this trade again" button, since that would
imply a use case beyond what this sprint's scope covers).

## 8. CORS opened to POST, for exactly one endpoint
`allow_methods` on the CORS middleware went from `["GET"]` to `["GET", "POST"]` - the only
non-GET endpoint a browser calls is the report-generation trigger, and it still only ever
schedules a background task server-side, never blocks. No other POST-from-browser surface
exists or is implied by this change.

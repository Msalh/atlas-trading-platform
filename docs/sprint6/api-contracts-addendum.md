# Sprint 6 - API Contract Addendum

## `GET /api/v1/ai/notes`
Query params: `trade_correlation_id` (optional), `note_type` (optional, one of
`entry_score` / `post_trade_review` / `daily_report` / `weekly_report`), `limit`
(default 50, max 200). Filters are AND-ed.
```json
{
  "count": 2,
  "notes": [
    {
      "id": 12,
      "trade_correlation_id": "2026-07-07T17:35:00Z",
      "note_type": "entry_score",
      "created_at": "2026-07-07T17:35:02+00:00",
      "model": "claude-haiku-4-5-20251001",
      "score": 8,
      "score_label": "Strong Alignment",
      "content": "Regime slope is steep and the sweep is fresh...",
      "error": null
    }
  ]
}
```
`score`/`score_label` are always `null` for `post_trade_review`/`daily_report`/
`weekly_report` note types (only `entry_score` produces them). `error` is set (and
`content`/`score`/`score_label` are `null`) when the underlying Claude call failed or
`ANTHROPIC_API_KEY` isn't configured - this is never hidden as a silent success.

## `GET /api/v1/ai/reports`
Query params: `period` (optional, `daily` or `weekly` - omit for both combined,
newest first), `limit` (default 20, max 100). Same row shape as `/ai/notes`, filtered
to `note_type` in (`daily_report`, `weekly_report`); `trade_correlation_id` is always
`null` on these rows.

## `POST /api/v1/ai/reports/{period}`
`{period}` must be `daily` or `weekly`. Schedules report generation as a background
task and returns immediately - **does not wait for Claude**.
```json
{ "ok": true, "status": "generating", "period": "daily" }
```
Response: `202 Accepted` on success, `400` if `{period}` is invalid. Poll
`GET /api/v1/ai/reports?period={period}` afterward (or wait for the `ai.report_generated`
SSE event - see below) to see the result once generation finishes, typically a few
seconds later.

## New timeline event types on `GET /api/v1/trades/{correlation_id}`
Two new possible entries in the `timeline` array (see `docs/sprint2/api-contracts-addendum.md`
for the base shape), replacing what used to be a single `ai_analysis` entry:
```json
{ "type": "entry_score", "at": "2026-07-07T17:35:02+00:00", "score": 8, "score_label": "Strong Alignment", "content": "...", "error": null }
{ "type": "post_trade_review", "at": "2026-07-07T18:12:09+00:00", "content": "...", "error": null }
```
`entry_score` appears right after `pmt_forwarded`/`pmt_forward_failed`; `post_trade_review`
appears after `exit`, since it can only be generated once the trade has actually closed.
The legacy `ai_analysis` event type (`"at": null` always) still appears for trades that
predate this migration and only have the old single-slot columns populated - never
alongside a real `entry_score` entry for the same trade.

## New SSE event types on `GET /api/v1/stream`
Three new possible `data.type` values (see `docs/sprint3/api-contracts-addendum.md` for
the wire format): `ai.entry_scored`, `ai.trade_reviewed`, `ai.report_generated`. Same
"invalidate and refetch" contract as every other event type - payloads are minimal
(`correlation_id`/`period` plus `ok`/`error`/`score`), not full note content.

## `claude` block on `GET /api/v1/status`
Unchanged shape, now reflects the most recent of all three new event types (previously
only the single old analysis event) - see `docs/sprint2/api-contracts-addendum.md` for
the base `/status` contract.

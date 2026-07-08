# Sprint 7 - API Contract Addendum

## `ai_notes` rows (`GET /api/v1/ai/notes`) gain four fields on `entry_score` rows
```json
{
  "id": 12,
  "trade_correlation_id": "corr-abc",
  "note_type": "entry_score",
  "created_at": "2026-07-07T17:35:02+00:00",
  "model": "claude-haiku-4-5-20251001",
  "score": 8,
  "score_label": "High Confidence",
  "content": "High Confidence (8/10) from 11 historically similar trades - regime slope and a fresh sweep both line up with the winning sample...",
  "error": null,
  "expected_r": 0.62,
  "historical_win_rate_pct": 75.0,
  "similar_trade_count": 11,
  "factors": [
    { "name": "regime_slope_pct", "entry_value": 1.4, "winners_median": 1.1, "losers_median": 0.4, "favorable": true },
    { "name": "ema_distance_atr", "entry_value": 0.6, "winners_median": 0.5, "losers_median": 1.6, "favorable": true },
    { "name": "sweep_age_bars", "entry_value": 4, "winners_median": 3, "losers_median": 10, "favorable": true }
  ]
}
```
`score_label` is now one of `High Confidence` / `Moderate Confidence` / `Low Confidence` /
`Insufficient History` (replacing Sprint 6's `Strong Alignment` / `Moderate Alignment` /
`Weak Alignment` / `Chop Risk`, which were labels Claude produced itself and no longer
apply). `expected_r`/`historical_win_rate_pct`/`similar_trade_count`/`factors` are `null` on
every `post_trade_review`/`daily_report`/`weekly_report` row, and also `null` on an
`entry_score` row when `similar_trade_count` is `0` (nothing to compute against yet - see
architecture-decisions.md #4). Unlike Sprint 6, `error` being set does **not** imply `score`
is `null` - the score is computed independently of Claude (see architecture-decisions.md #5).

## `GET /api/v1/ai/intelligence/{correlation_id}` (new)
On-demand, synchronous recomputation - no Claude call, nothing persisted. Works for any
trade (open or closed).
```json
{
  "correlation_id": "corr-abc",
  "similar_trade_count": 11,
  "confidence_score": 8,
  "confidence_label": "High Confidence",
  "summary": {
    "total_trades": 11, "wins": 8, "losses": 3, "win_rate_pct": 72.7,
    "gross_profit": 3200.0, "gross_loss": 900.0, "profit_factor": 3.56,
    "expectancy": 209.1, "avg_win": 400.0, "avg_loss": -300.0,
    "avg_r": 0.62, "r_multiple_sample_size": 11
  },
  "factors": [
    { "name": "regime_slope_pct", "entry_value": 1.4, "winners_median": 1.1, "losers_median": 0.4, "favorable": true },
    { "name": "ema_distance_atr", "entry_value": 0.6, "winners_median": 0.5, "losers_median": 1.6, "favorable": true },
    { "name": "sweep_age_bars", "entry_value": 4, "winners_median": 3, "losers_median": 10, "favorable": true }
  ]
}
```
`summary` is exactly the `AnalyticsSummaryResponse` shape from `docs/sprint5/api-contracts-addendum.md`,
computed over the similar-trades subset rather than the whole account. `404` if
`{correlation_id}` doesn't match any stored trade. `confidence_score` is `null` and
`confidence_label` is `"Insufficient History"` when `similar_trade_count` is `0`.

## New timeline event fields on `GET /api/v1/trades/{correlation_id}`
The `entry_score` timeline event (see `docs/sprint6/api-contracts-addendum.md` for the base
shape) gains the same four fields as the `ai_notes` row above:
```json
{
  "type": "entry_score", "at": "2026-07-07T17:35:02+00:00",
  "score": 8, "score_label": "High Confidence", "content": "...", "error": null,
  "expected_r": 0.62, "historical_win_rate_pct": 75.0, "similar_trade_count": 11,
  "factors": [ { "name": "regime_slope_pct", "...": "..." } ]
}
```

## No changes to SSE event types or `POST`/webhook contracts
`ai.entry_scored`'s payload shape is unchanged (`correlation_id`, `ok`, `score`, `error`) -
`score` is simply now sourced from `atlas/intelligence.py` instead of parsed from Claude's
text. The webhook request/response contract, `ai.trade_reviewed`, and `ai.report_generated`
are entirely untouched by this sprint.

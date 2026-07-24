// Sprint 11A Group 2. Typed client for GET /stats/today, reached through the
// same-origin BFF proxy (src/lib/proxyClient.ts). Shape mirrored from
// atlas/api/v1/stats.py's stats_today() response.
//
// "stats/today" is a new proxy allowlist entry, added alongside this client.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export interface StatsTodayResponse {
  date_utc: string;
  trades_entered_today: number;
  trades_closed_today: number;
  wins_today: number;
  losses_today: number;
  realized_pnl_today: number;
  pmt_forward_failures_today: number;
  open_position: {
    correlation_id: string | null;
    risk_points: number | null;
    reward_points: number | null;
  };
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isStatsTodayResponse(value: unknown): value is StatsTodayResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  if (
    typeof v.date_utc !== "string" ||
    typeof v.trades_entered_today !== "number" ||
    typeof v.trades_closed_today !== "number" ||
    typeof v.wins_today !== "number" ||
    typeof v.losses_today !== "number" ||
    typeof v.realized_pnl_today !== "number" ||
    typeof v.pmt_forward_failures_today !== "number"
  ) {
    return false;
  }

  if (typeof v.open_position !== "object" || v.open_position === null) return false;
  const openPosition = v.open_position as Record<string, unknown>;
  return (
    (openPosition.correlation_id === null || typeof openPosition.correlation_id === "string") &&
    isNullableNumber(openPosition.risk_points) &&
    isNullableNumber(openPosition.reward_points)
  );
}

export function fetchStatsToday(): Promise<StatsTodayResponse> {
  return proxyGet("stats/today", {}, isStatsTodayResponse);
}

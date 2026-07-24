// Sprint 11A Group 5. Typed client for GET /activity, reached through the
// same-origin BFF proxy (src/lib/proxyClient.ts). Shape mirrored from
// atlas/activity.py's ActivityEvent dataclass (the backend response is
// `asdict(e)` per event) - see atlas/api/v1/activity.py.
//
// "activity" (params: limit) is a new proxy allowlist entry, added
// alongside this client.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export type ActivityCategory = "trading" | "ai" | "risk" | "analytics" | "system";
export type ActivitySeverity = "info" | "success" | "warning" | "critical";

export interface ActivityEvent {
  id: string;
  timestamp: string;
  category: ActivityCategory;
  severity: ActivitySeverity;
  title: string;
  description: string | null;
  correlation_id: string | null;
}

export interface ActivityResponse {
  count: number;
  events: ActivityEvent[];
}

const CATEGORIES: readonly ActivityCategory[] = ["trading", "ai", "risk", "analytics", "system"];
const SEVERITIES: readonly ActivitySeverity[] = ["info", "success", "warning", "critical"];

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isActivityEvent(value: unknown): value is ActivityEvent {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "string" &&
    typeof v.timestamp === "string" &&
    typeof v.category === "string" &&
    (CATEGORIES as readonly string[]).includes(v.category) &&
    typeof v.severity === "string" &&
    (SEVERITIES as readonly string[]).includes(v.severity) &&
    typeof v.title === "string" &&
    isNullableString(v.description) &&
    isNullableString(v.correlation_id)
  );
}

function isActivityResponse(value: unknown): value is ActivityResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.count === "number" && Array.isArray(v.events) && v.events.every(isActivityEvent);
}

export function fetchActivity(params?: { limit?: number }): Promise<ActivityResponse> {
  const query: Record<string, string> = {};
  if (params?.limit !== undefined) query.limit = String(params.limit);
  return proxyGet("activity", query, isActivityResponse);
}

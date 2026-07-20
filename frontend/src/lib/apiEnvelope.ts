// UI v2. The shared HTTP response envelope every new UI v2 endpoint returns
// (architecture doc §6) - source_track distinguishes LIVE (recomputed fresh)
// from FROZEN (checked-in snapshot) responses, and code_version is ALWAYS
// source_computation_version, never snapshot_exporter_version (amendment 2).
// Callers must read provenance from this envelope, never infer it from
// which endpoint they called.

export type SourceTrack = "live" | "frozen";

export interface ResponseEnvelope {
  schema_version: string;
  source_track: SourceTrack;
  symbol: string;
  timeframe: string;
  generated_at: string;
  data_as_of: string;
  code_version: string | null;
  warnings: string[];
}

export function isResponseEnvelope(value: unknown): value is ResponseEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.schema_version === "string" &&
    (v.source_track === "live" || v.source_track === "frozen") &&
    typeof v.symbol === "string" &&
    typeof v.timeframe === "string" &&
    typeof v.generated_at === "string" &&
    typeof v.data_as_of === "string" &&
    (typeof v.code_version === "string" || v.code_version === null) &&
    Array.isArray(v.warnings) &&
    v.warnings.every((w) => typeof w === "string")
  );
}

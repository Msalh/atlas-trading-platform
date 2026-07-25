/**
 * Frozen Phase 17E reader contract consumed by the Phase 17F browser.
 *
 * This module describes transport data only. It does not model canonical bytes
 * and must not be used to reconstruct atlas-jcs.v1 evidence.
 */

export const SNAPSHOT_API_SCHEMA_VERSION = "snapshot_private_api.v1" as const;
export const SNAPSHOT_SCHEMA_VERSION = "trader_now_snapshot.v1" as const;
export const SNAPSHOT_PAGE_SIZES = [25, 50, 100] as const;
export const SNAPSHOT_DEFAULT_PAGE_SIZE = 50;
export const SNAPSHOT_MAX_CURSOR_LENGTH = 1024;
export const SNAPSHOT_CORRELATION_HEADER = "X-Correlation-ID" as const;

export const SNAPSHOT_READER_ROUTES = {
  list: "/api/v1/snapshots",
  detail: (snapshotId: string) => `/api/v1/snapshots/${snapshotId}`,
  metadata: (snapshotId: string) =>
    `/api/v1/snapshots/${snapshotId}/metadata`,
  integrity: (snapshotId: string) =>
    `/api/v1/snapshots/${snapshotId}/integrity`,
} as const;

export type JsonPrimitive = boolean | number | string | null;
export type JsonValue =
  | JsonPrimitive
  | { readonly [key: string]: JsonValue }
  | readonly JsonValue[];

export interface SnapshotMetadata {
  readonly schema_version: typeof SNAPSHOT_API_SCHEMA_VERSION;
  readonly snapshot_id: string;
  readonly evidence_digest: string;
  readonly created_at: string;
  readonly evaluated_at: string | null;
  readonly latest_closed_at: string | null;
  readonly economic_instrument: string | null;
  readonly market_data_provider: string | null;
  readonly market_data_series_symbol: string | null;
  readonly market_data_series_type: string | null;
  readonly timeframe: string;
  readonly strategy_id: string;
  readonly strategy_version: string;
  readonly trust_status: string;
  readonly supersedes_snapshot_id: string | null;
}

export interface SnapshotListResponse {
  readonly schema_version: typeof SNAPSHOT_API_SCHEMA_VERSION;
  readonly items: readonly SnapshotMetadata[];
  /** Opaque server-issued cursor. The browser must never decode this value. */
  readonly next_cursor: string | null;
}

export interface SnapshotDetailResponse {
  readonly schema_version: typeof SNAPSHOT_API_SCHEMA_VERSION;
  /**
   * Semantic transport representation of the verified snapshot.
   * This is not the authoritative canonical UTF-8 byte stream.
   */
  readonly snapshot: Readonly<Record<string, JsonValue>>;
}

export interface SnapshotIntegrityResponse {
  readonly schema_version: typeof SNAPSHOT_API_SCHEMA_VERSION;
  readonly snapshot_id: string;
  readonly evidence_digest: string;
  readonly valid: true;
}

export interface SnapshotErrorResponse {
  readonly schema_version: typeof SNAPSHOT_API_SCHEMA_VERSION;
  readonly code: string;
  readonly message: string;
  readonly correlation_id: string;
}

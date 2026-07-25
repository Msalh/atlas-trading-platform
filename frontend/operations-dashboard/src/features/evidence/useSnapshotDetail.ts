"use client";

import { useEffect, useState } from "react";
import {
  SNAPSHOT_API_SCHEMA_VERSION,
  isSnapshotId,
  type SnapshotMetadata,
} from "./contract";
import {
  projectSemanticSnapshot,
  SemanticProjectionError,
  type SemanticEvidenceProjection,
} from "./semanticProjection";

export interface SnapshotDetailHeader {
  readonly snapshotId: string;
  readonly snapshotSchemaVersion: string;
}

export type SnapshotDetailState =
  | { readonly status: "loading" }
  | {
      readonly status: "ready";
      readonly header: SnapshotDetailHeader;
      readonly metadata: SnapshotMetadata;
      readonly semanticEvidence: SemanticEvidenceProjection;
      readonly formattedJson: string;
    }
  | { readonly status: "error"; readonly code: string };

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function metadataFrom(value: unknown, snapshotId: string): SnapshotMetadata | null {
  if (!isObject(value)) return null;
  if (
    value.schema_version !== SNAPSHOT_API_SCHEMA_VERSION ||
    value.snapshot_id !== snapshotId ||
    typeof value.evidence_digest !== "string" ||
    !/^[0-9a-f]{64}$/.test(value.evidence_digest) ||
    typeof value.created_at !== "string" ||
    !isNullableString(value.evaluated_at) ||
    !isNullableString(value.latest_closed_at) ||
    !isNullableString(value.economic_instrument) ||
    !isNullableString(value.market_data_provider) ||
    !isNullableString(value.market_data_series_symbol) ||
    !isNullableString(value.market_data_series_type) ||
    typeof value.timeframe !== "string" ||
    typeof value.strategy_id !== "string" ||
    typeof value.strategy_version !== "string" ||
    typeof value.trust_status !== "string" ||
    !isNullableString(value.supersedes_snapshot_id)
  ) {
    return null;
  }
  return value as unknown as SnapshotMetadata;
}

function metadataMatchesEvidence(
  metadata: SnapshotMetadata,
  evidence: SemanticEvidenceProjection,
): boolean {
  return (
    metadata.economic_instrument === evidence.identity.product &&
    metadata.market_data_provider === evidence.market.provider &&
    metadata.market_data_series_symbol === evidence.market.seriesSymbol &&
    metadata.market_data_series_type === evidence.market.seriesType &&
    metadata.timeframe === evidence.identity.timeframe &&
    metadata.strategy_id === evidence.identity.strategyId &&
    metadata.strategy_version === evidence.identity.strategyVersion &&
    metadata.trust_status === evidence.trust.status &&
    metadata.evaluated_at === evidence.evaluatedAt &&
    metadata.latest_closed_at === evidence.market.latestClosedAt
  );
}

async function responseErrorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      isObject(body) &&
      typeof body.code === "string"
    ) {
      return body.code;
    }
  } catch {
    // Dashboard authentication can return a non-JSON response.
  }
  if (response.status === 401) return "dashboard_authentication_required";
  if (response.status === 403) return "snapshot_access_forbidden";
  if (response.status === 404) return "snapshot_not_found";
  if (response.status === 409) return "snapshot_integrity_failed";
  return "snapshot_detail_unavailable";
}

function preferredError(
  detail: { response: Response; code: string },
  metadata: { response: Response; code: string },
): string {
  const codes = [detail, metadata];
  return (
    codes.find(({ response }) => response.status === 409)?.code ??
    codes.find(({ response }) => response.status === 401)?.code ??
    codes.find(({ response }) => response.status === 403)?.code ??
    codes.find(({ response }) => response.status === 404)?.code ??
    codes.find(({ response }) => !response.ok)?.code ??
    "snapshot_detail_unavailable"
  );
}

export function useSnapshotDetail(snapshotId: string): SnapshotDetailState {
  const [state, setState] = useState<SnapshotDetailState>({
    status: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const load = async () => {
      if (!isSnapshotId(snapshotId)) {
        setState({ status: "error", code: "invalid_snapshot_id" });
        return;
      }
      setState({ status: "loading" });
      try {
        const [detailResponse, metadataResponse] = await Promise.all([
          fetch(`/api/evidence/snapshots/${snapshotId}`, {
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: controller.signal,
          }),
          fetch(`/api/evidence/snapshots/${snapshotId}/metadata`, {
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: controller.signal,
          }),
        ]);
        if (!current) return;
        if (!detailResponse.ok || !metadataResponse.ok) {
          const [detailCode, metadataCode] = await Promise.all([
            responseErrorCode(detailResponse),
            responseErrorCode(metadataResponse),
          ]);
          if (!current) return;
          setState({
            status: "error",
            code: preferredError(
              { response: detailResponse, code: detailCode },
              { response: metadataResponse, code: metadataCode },
            ),
          });
          return;
        }
        const [detailBody, metadataBody]: [unknown, unknown] = await Promise.all([
          detailResponse.json(),
          metadataResponse.json(),
        ]);
        if (!current) return;
        const metadata = metadataFrom(metadataBody, snapshotId);
        if (!metadata) {
          setState({
            status: "error",
            code: "unexpected_snapshot_response",
          });
          return;
        }
        let semantic;
        try {
          semantic = projectSemanticSnapshot(detailBody, snapshotId);
        } catch (error) {
          const code =
            error instanceof SemanticProjectionError
              ? error.code
              : "invalid_semantic_response";
          setState({
            status: "error",
            code,
          });
          return;
        }
        if (!metadataMatchesEvidence(metadata, semantic.evidence)) {
          setState({
            status: "error",
            code: "unexpected_snapshot_response",
          });
          return;
        }
        setState({
          status: "ready",
          header: {
            snapshotId: semantic.snapshotId,
            snapshotSchemaVersion: semantic.snapshotSchemaVersion,
          },
          metadata,
          semanticEvidence: semantic.evidence,
          formattedJson: semantic.formattedJson,
        });
      } catch (error) {
        if (
          !current ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          return;
        }
        setState({ status: "error", code: "snapshot_detail_unavailable" });
      }
    };
    const initialLoad = window.setTimeout(() => void load(), 0);
    return () => {
      current = false;
      window.clearTimeout(initialLoad);
      controller.abort();
    };
  }, [snapshotId]);

  return state;
}

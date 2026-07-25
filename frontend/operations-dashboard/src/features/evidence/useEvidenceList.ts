"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  SNAPSHOT_API_SCHEMA_VERSION,
  SNAPSHOT_DEFAULT_PAGE_SIZE,
  SNAPSHOT_MAX_CURSOR_LENGTH,
  isSnapshotId,
  type SnapshotListResponse,
  type SnapshotMetadata,
} from "./contract";
import {
  LOCAL_RESPONSE_LIMITS,
  hasErrorEnvelopeMarkers,
  readBoundedJson,
  safeErrorCode,
} from "./clientTransport";

export type EvidenceListState =
  | { readonly status: "loading"; readonly items: readonly SnapshotMetadata[] }
  | { readonly status: "ready"; readonly items: readonly SnapshotMetadata[] }
  | { readonly status: "empty"; readonly items: readonly SnapshotMetadata[] }
  | {
      readonly status: "error";
      readonly items: readonly SnapshotMetadata[];
      readonly code: string;
    };

interface EvidenceListController {
  readonly state: EvidenceListState;
  readonly pageSize: number;
  readonly pageNumber: number;
  readonly hasPrevious: boolean;
  readonly hasNext: boolean;
  readonly next: () => void;
  readonly previous: () => void;
  readonly latest: () => void;
  readonly refresh: () => void;
  readonly changePageSize: (pageSize: number) => void;
}

function isSnapshotListResponse(value: unknown): value is SnapshotListResponse {
  if (
    typeof value !== "object" ||
    value === null ||
    Array.isArray(value) ||
    hasErrorEnvelopeMarkers(value)
  ) {
    return false;
  }
  const response = value as Record<string, unknown>;
  const keys = Object.keys(response);
  return (
    keys.length === 3 &&
    ["schema_version", "items", "next_cursor"].every((key) =>
      keys.includes(key),
    ) &&
    response.schema_version === SNAPSHOT_API_SCHEMA_VERSION &&
    Array.isArray(response.items) &&
    response.items.every(isSnapshotMetadata) &&
    (response.next_cursor === null ||
      (typeof response.next_cursor === "string" &&
        response.next_cursor.length > 0 &&
        response.next_cursor.length <= SNAPSHOT_MAX_CURSOR_LENGTH))
  );
}

function nullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isSnapshotMetadata(value: unknown): value is SnapshotMetadata {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    Object.keys(item).length === 15 &&
    item.schema_version === SNAPSHOT_API_SCHEMA_VERSION &&
    typeof item.snapshot_id === "string" &&
    isSnapshotId(item.snapshot_id) &&
    typeof item.evidence_digest === "string" &&
    /^[0-9a-f]{64}$/.test(item.evidence_digest) &&
    typeof item.created_at === "string" &&
    nullableString(item.evaluated_at) &&
    nullableString(item.latest_closed_at) &&
    nullableString(item.economic_instrument) &&
    nullableString(item.market_data_provider) &&
    nullableString(item.market_data_series_symbol) &&
    nullableString(item.market_data_series_type) &&
    typeof item.timeframe === "string" &&
    typeof item.strategy_id === "string" &&
    typeof item.strategy_version === "string" &&
    typeof item.trust_status === "string" &&
    nullableString(item.supersedes_snapshot_id)
  );
}

export function useEvidenceList(): EvidenceListController {
  const [state, setState] = useState<EvidenceListState>({
    status: "loading",
    items: [],
  });
  const [pageSize, setPageSize] = useState(SNAPSHOT_DEFAULT_PAGE_SIZE);
  const [pageNumber, setPageNumber] = useState(1);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  const currentCursor = useRef<string | null>(null);
  const cursorHistory = useRef<(string | null)[]>([]);
  const currentPageSize = useRef(SNAPSHOT_DEFAULT_PAGE_SIZE);
  const currentResponse = useRef<SnapshotListResponse | null>(null);
  const requestSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  const load = useCallback(
    async (cursor: string | null, requestedPageSize: number) => {
      const sequence = ++requestSequence.current;
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      setHasNext(false);
      setState((existing) => ({
        status: "loading",
        items: existing.items,
      }));

      const query = new URLSearchParams({ limit: String(requestedPageSize) });
      if (cursor !== null) query.set("cursor", cursor);
      try {
        const response = await fetch(`/api/evidence/snapshots?${query}`, {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        });
        if (sequence !== requestSequence.current) return;
        if (!response.ok) {
          const code = await safeErrorCode(
            response,
            "evidence_list_unavailable",
          );
          if (sequence !== requestSequence.current) return;
          currentResponse.current = null;
          setHasNext(false);
          setState({
            status: "error",
            items: [],
            code,
          });
          return;
        }
        const body = await readBoundedJson(
          response,
          LOCAL_RESPONSE_LIMITS.list,
        );
        if (sequence !== requestSequence.current) return;
        if (!isSnapshotListResponse(body)) {
          currentResponse.current = null;
          setHasNext(false);
          setState({
            status: "error",
            items: [],
            code: "unexpected_evidence_response",
          });
          return;
        }
        currentResponse.current = body;
        setHasNext(body.next_cursor !== null);
        setState({
          status: body.items.length === 0 ? "empty" : "ready",
          items: body.items,
        });
      } catch (error) {
        if (
          sequence !== requestSequence.current ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          return;
        }
        currentResponse.current = null;
        setHasNext(false);
        setState({
          status: "error",
          items: [],
          code: "evidence_list_unavailable",
        });
      }
    },
    [],
  );

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void load(null, SNAPSHOT_DEFAULT_PAGE_SIZE);
    }, 0);
    return () => {
      window.clearTimeout(initialLoad);
      requestSequence.current += 1;
      activeRequest.current?.abort();
    };
  }, [load]);

  const next = useCallback(() => {
    const nextCursor = currentResponse.current?.next_cursor;
    if (!nextCursor) return;
    cursorHistory.current = [...cursorHistory.current, currentCursor.current];
    currentCursor.current = nextCursor;
    setHasPrevious(true);
    setPageNumber(cursorHistory.current.length + 1);
    void load(nextCursor, currentPageSize.current);
  }, [load]);

  const previous = useCallback(() => {
    if (cursorHistory.current.length === 0) return;
    const history = cursorHistory.current.slice();
    const previousCursor = history.pop() ?? null;
    cursorHistory.current = history;
    currentCursor.current = previousCursor;
    setHasPrevious(history.length > 0);
    setPageNumber(history.length + 1);
    void load(previousCursor, currentPageSize.current);
  }, [load]);

  const latest = useCallback(() => {
    cursorHistory.current = [];
    currentCursor.current = null;
    setHasPrevious(false);
    setPageNumber(1);
    void load(null, currentPageSize.current);
  }, [load]);

  const refresh = useCallback(() => {
    void load(currentCursor.current, currentPageSize.current);
  }, [load]);

  const changePageSize = useCallback(
    (nextPageSize: number) => {
      if (![25, 50, 100].includes(nextPageSize)) return;
      cursorHistory.current = [];
      currentCursor.current = null;
      currentPageSize.current = nextPageSize;
      setHasPrevious(false);
      setPageSize(nextPageSize);
      setPageNumber(1);
      void load(null, nextPageSize);
    },
    [load],
  );

  return {
    state,
    pageSize,
    pageNumber,
    hasPrevious,
    hasNext,
    next,
    previous,
    latest,
    refresh,
    changePageSize,
  };
}

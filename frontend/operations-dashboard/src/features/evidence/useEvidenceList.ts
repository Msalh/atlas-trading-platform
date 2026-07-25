"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  SNAPSHOT_DEFAULT_PAGE_SIZE,
  type SnapshotListResponse,
  type SnapshotMetadata,
} from "./contract";

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
  if (typeof value !== "object" || value === null) return false;
  const response = value as Partial<SnapshotListResponse>;
  return (
    response.schema_version === "snapshot_private_api.v1" &&
    Array.isArray(response.items) &&
    (response.next_cursor === null ||
      typeof response.next_cursor === "string")
  );
}

async function errorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "code" in body &&
      typeof body.code === "string"
    ) {
      return body.code;
    }
  } catch {
    // The dashboard boundary may return a non-JSON authentication response.
  }
  return response.status === 401
    ? "dashboard_authentication_required"
    : "evidence_list_unavailable";
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
          const code = await errorCode(response);
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
        const body: unknown = await response.json();
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

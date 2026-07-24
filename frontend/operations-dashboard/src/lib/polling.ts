"use client";

import { useEffect, useRef, useState } from "react";
import type { DashboardSnapshot } from "@/lib/types";

const NORMAL_DELAY = 10_000;
const FAILURE_DELAY = 20_000;
const TIMEOUT = 7_000;

async function getJson(path: string, signal: AbortSignal) {
  const response = await fetch(path, { cache: "no-store", signal });
  if (!response.ok) {
    const error = new Error(response.status === 401 ? "authentication" : "unavailable");
    Object.assign(error, { status: response.status });
    throw error;
  }
  return { body: await response.json(), correlationId: response.headers.get("x-correlation-id") };
}

export function useOperationsPolling() {
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [state, setState] = useState<"polling" | "paused" | "backoff" | "auth-failed">("polling");
  const [stale, setStale] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      if (!active || document.hidden) {
        if (active) {
          setState("paused");
          setStale(true);
        }
        return;
      }
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TIMEOUT);
      let nextDelay: number | null = NORMAL_DELAY;
      try {
        const [health, readiness, latest, operations] = await Promise.all([
          getJson("/api/status/health", controller.signal),
          getJson("/api/status/readiness", controller.signal),
          getJson("/api/status/latest", controller.signal),
          getJson("/api/status/operations", controller.signal),
        ]);
        if (!active) return;
        setData({
          health: health.body,
          readiness: readiness.body,
          latest: latest.body,
          operations: operations.body,
          correlationId: latest.correlationId,
        });
        setLastRefresh(new Date());
        setStale(false);
        setState("polling");
      } catch (error) {
        if (!active) return;
        setStale(true);
        if ((error as { status?: number }).status === 401) {
          setState("auth-failed");
          nextDelay = null;
        } else {
          setState("backoff");
          nextDelay = FAILURE_DELAY;
        }
      } finally {
        clearTimeout(timeout);
        if (active && nextDelay !== null) timer.current = setTimeout(refresh, nextDelay);
      }
    };
    void refresh();
    const visibility = () => {
      if (timer.current) clearTimeout(timer.current);
      if (document.hidden) {
        setState("paused");
        setStale(true);
      } else {
        void refresh();
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", visibility);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return { data, lastRefresh, state, stale };
}

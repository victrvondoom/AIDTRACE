"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Keep reads current without overlapping polls or accepting superseded responses.
 * Memoize query with useCallback; manual refresh supersedes any pending read.
 * Errors retain the last successful value and its timestamp for explicit stale UI.
 */
export function useLiveQuery<T>(query: () => Promise<T>, intervalMs = 30000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const generation = useRef(0);
  const active = useRef(false);
  const pending = useRef(false);

  const refresh = useCallback(async (): Promise<T | null> => {
    const request = ++generation.current;
    pending.current = true;
    if (active.current) setRefreshing(true);
    try {
      const result = await query();
      if (active.current && request === generation.current) {
        setData(result); setError(null); setUpdatedAt(new Date().toISOString());
      }
      return result;
    } catch (cause) {
      if (active.current && request === generation.current) setError(cause instanceof Error ? cause.message : "Could not refresh data.");
      return null;
    } finally {
      if (request === generation.current) {
        pending.current = false;
        if (active.current) setRefreshing(false);
      }
    }
  }, [query]);

  const invalidate = useCallback(() => {
    active.current = false; generation.current++; pending.current = false;
  }, []);

  useEffect(() => {
    active.current = true;
    const initial = window.setTimeout(() => void refresh(), 0);
    const resume = () => { if (!document.hidden && navigator.onLine && !pending.current) void refresh(); };
    const timer = window.setInterval(resume, Math.max(15000, intervalMs));
    window.addEventListener("focus", resume);
    window.addEventListener("online", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      invalidate();
      window.clearTimeout(initial);
      window.clearInterval(timer);
      window.removeEventListener("focus", resume);
      window.removeEventListener("online", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [refresh, intervalMs, invalidate]);

  return { data, error, refreshing, loading: data === null && refreshing, updatedAt, refresh };
}

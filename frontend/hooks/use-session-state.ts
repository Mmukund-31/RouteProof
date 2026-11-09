"use client";
import { useCallback, useEffect, useState } from "react";

/**
 * useState that survives navigation within the tab (sessionStorage). Lists use it so opening a record and coming
 * back keeps the search, filters, sort and page. Restored after mount so server and first client render agree;
 * storage failures (private mode, blocked) fall back to plain state.
 */
export function useSessionState<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [v, setV] = useState<T>(initial);
  useEffect(() => {
    try {
      const s = sessionStorage.getItem(key);
      if (s !== null) {
        const parsed = JSON.parse(s);
        // Merge objects so a stored value from an older shape still gets new keys.
        setV(initial && typeof initial === "object" && !Array.isArray(initial) && parsed && typeof parsed === "object" ? { ...initial, ...parsed } : parsed);
      }
    } catch { /* storage blocked or malformed */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const set = useCallback((n: T | ((p: T) => T)) => {
    setV((p) => {
      const next = typeof n === "function" ? (n as (p: T) => T)(p) : n;
      try { sessionStorage.setItem(key, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }, [key]);
  return [v, set];
}

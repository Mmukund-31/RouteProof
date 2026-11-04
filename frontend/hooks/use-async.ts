"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> { data: T | null; loading: boolean; error: string | null; reload: () => void }

/** Loads data whenever `deps` change; stale responses are ignored. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    const my = ++seq.current;
    setLoading(true);
    setError(null);
    fnRef.current()
      .then((r) => { if (my === seq.current) setData(r); })
      .catch((e: Error) => { if (my === seq.current) setError(e.message); })
      .finally(() => { if (my === seq.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, loading, error, reload };
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

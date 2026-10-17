"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncState<T> = {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  /** Fetch again. Results from older, slower requests are discarded. */
  reload: () => Promise<void>;
  /** Replace the data locally, e.g. after a mutation returned the new value. */
  setData: (data: T) => void;
};

export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  const run = useCallback(load, deps);

  const reload = useCallback(async () => {
    const id = ++latest.current;
    setLoading(true);
    try {
      const result = await run();
      if (id === latest.current) {
        setData(result);
        setError(undefined);
      }
    } catch (err) {
      if (id === latest.current) setError(err as Error);
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }, [run]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

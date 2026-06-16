// P4 — live job overlay (service). Owns the single SSE connection and exposes
// per-job live events via an external store so ONLY the changed row re-renders
// (CLAUDE.md: split context by update frequency — a 4000-unit job's event flood
// must not re-render the whole list every frame). Separately, a trailing throttle
// invalidates the ['jobs'] queries at most once / THROTTLE_MS so the flood can't
// hammer the list endpoint; this also pulls in brand-new job rows.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { useJobsStream, type ConnectionState } from '../hooks/useJobsStream';
import { jobKey, type JobSseEvent } from '../types';

const THROTTLE_MS = 1500;

type Store = {
  get(key: string): JobSseEvent | undefined;
  subscribe(key: string, cb: () => void): () => void;
};

const StoreCtx = createContext<Store | null>(null);
const StateCtx = createContext<ConnectionState>('idle');

export function JobsStreamProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();

  const overlay = useRef(new Map<string, JobSseEvent>());
  const listeners = useRef(new Map<string, Set<() => void>>());
  const throttleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const notify = useCallback((key: string) => {
    const subs = listeners.current.get(key);
    if (subs) for (const cb of subs) cb();
  }, []);

  const scheduleInvalidate = useCallback(() => {
    if (throttleTimer.current) return; // trailing throttle — one pending flush
    throttleTimer.current = setTimeout(() => {
      throttleTimer.current = null;
      void qc.invalidateQueries({ queryKey: ['jobs'] });
    }, THROTTLE_MS);
  }, [qc]);

  const onEvent = useCallback(
    (ev: JobSseEvent) => {
      const key = jobKey(ev);
      overlay.current.set(key, ev);
      notify(key);
      scheduleInvalidate();
    },
    [notify, scheduleInvalidate],
  );

  const state = useJobsStream(accessToken, onEvent);

  useEffect(
    () => () => {
      if (throttleTimer.current) clearTimeout(throttleTimer.current);
    },
    [],
  );

  const store = useMemo<Store>(
    () => ({
      get: (key) => overlay.current.get(key),
      subscribe: (key, cb) => {
        let subs = listeners.current.get(key);
        if (!subs) {
          subs = new Set();
          listeners.current.set(key, subs);
        }
        subs.add(cb);
        return () => {
          subs!.delete(cb);
          if (subs!.size === 0) listeners.current.delete(key);
        };
      },
    }),
    [],
  );

  return (
    <StoreCtx.Provider value={store}>
      <StateCtx.Provider value={state}>{children}</StateCtx.Provider>
    </StoreCtx.Provider>
  );
}

/** Live SSE event for one job key (undefined until an event arrives). Subscribes
 *  to JUST this key so unrelated job updates don't re-render the consumer. */
export function useJobLive(key: string): JobSseEvent | undefined {
  const store = useContext(StoreCtx);
  return useSyncExternalStore(
    useCallback((cb) => (store ? store.subscribe(key, cb) : () => {}), [store, key]),
    () => store?.get(key),
  );
}

export function useJobsConnection(): ConnectionState {
  return useContext(StateCtx);
}

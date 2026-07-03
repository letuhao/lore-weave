import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import { useChatSession } from '../providers';
import type { ContextHistoryPoint } from '../types';

// W1-residual — the per-turn token-history controller (MVC: this hook owns the
// fetch + state; ContextHistoryChart only renders what it's handed). Lazily
// loads the series (only once `enabled` — the History tab — is opened) for the
// active session and maps the API rows into typed points ordered oldest→newest.
// A useEffect here is legitimate synchronization: fetch-on-enable, not
// event-handling. The chart re-flattens the nested memory_knowledge itself.

export interface ContextHistoryState {
  points: ContextHistoryPoint[];
  loading: boolean;
  error: string | null;
  /** Re-fetch on demand (e.g. a "refresh" affordance / after a new turn). */
  reload: () => void;
}

export function useContextHistory(enabled: boolean): ContextHistoryState {
  const { accessToken } = useAuth();
  const { activeSession } = useChatSession();
  const sessionId = activeSession?.session_id ?? null;

  const [points, setPoints] = useState<ContextHistoryPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // `shouldApply` is the in-flight guard: the effect passes `() => !ignore` so a
  // resolution that lost the race (its session already switched away) is
  // dropped instead of clobbering the current session's state. `reload` passes
  // the default (always-apply) since it targets the current session.
  const load = useCallback(
    async (shouldApply: () => boolean = () => true) => {
      if (!accessToken || !sessionId) return;
      setLoading(true);
      setError(null);
      try {
        const res = await chatApi.getContextHistory(accessToken, sessionId);
        if (!shouldApply()) return;
        // Map defensively — the server orders oldest→newest, but a missing/empty
        // items array degrades to [] rather than throwing.
        setPoints(Array.isArray(res?.items) ? res.items : []);
      } catch (err) {
        if (!shouldApply()) return;
        setError((err as Error)?.message ?? 'failed to load context history');
        setPoints([]);
      } finally {
        // Only the winning fetch owns the loading flag — a stale one must not
        // flip it off while the current fetch is still running.
        if (shouldApply()) setLoading(false);
      }
    },
    [accessToken, sessionId],
  );

  // Clear stale bars the instant the session switches so the chart falls back to
  // its spinner/empty state rather than showing the PREVIOUS session's history
  // while the new fetch is in flight. Keyed to sessionId only (NOT `enabled`) so
  // toggling the History tab preserves the already-loaded series (no refetch
  // flicker on toggle).
  useEffect(() => {
    setPoints([]);
  }, [sessionId]);

  // Fetch when the History tab is enabled (or the active session changes while
  // it is open). Not on every render — only while enabled. The `ignore` flag +
  // cleanup drop a stale resolution: on a fast session switch, session A's
  // slower fetch must not overwrite B's freshly-loaded state.
  useEffect(() => {
    if (!enabled || !sessionId) return;
    let ignore = false;
    void load(() => !ignore);
    return () => {
      ignore = true;
    };
  }, [enabled, sessionId, load]);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  return { points, loading, error, reload };
}

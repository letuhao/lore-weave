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

  const load = useCallback(async () => {
    if (!accessToken || !sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await chatApi.getContextHistory(accessToken, sessionId);
      // Map defensively — the server orders oldest→newest, but a missing/empty
      // items array degrades to [] rather than throwing.
      setPoints(Array.isArray(res?.items) ? res.items : []);
    } catch (err) {
      setError((err as Error)?.message ?? 'failed to load context history');
      setPoints([]);
    } finally {
      setLoading(false);
    }
  }, [accessToken, sessionId]);

  // Fetch when the History tab first opens (or the active session changes while
  // it is open). Not on every render — only while enabled.
  useEffect(() => {
    if (!enabled || !sessionId) return;
    void load();
  }, [enabled, sessionId, load]);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  return { points, loading, error, reload };
}

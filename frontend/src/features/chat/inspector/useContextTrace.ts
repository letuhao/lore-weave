import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatSession, ContextTracePoint } from '../types';

// Context Compiler · Trace Inspector controller (MVC: this hook owns the fetch +
// state; the view only renders). SELF-CONTAINED — it lists the user's sessions
// and picks one (default: most recent) so it works both inside the studio dock
// AND as a standalone page, without depending on a chat-session provider being in
// the tree. `enabled` gates the fetch (the panel is mounted-but-hidden per MVC).

/** Poll cadence for live turn updates (§11a "live update … poll"). */
export const POLL_INTERVAL_MS = 20000;

export interface ContextTraceState {
  sessions: ChatSession[];
  sessionId: string | null;
  selectSession: (id: string) => void;
  points: ContextTracePoint[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useContextTrace(
  enabled: boolean,
  initialSessionId?: string | null,
): ContextTraceState {
  const { accessToken } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId ?? null);
  const [points, setPoints] = useState<ContextTracePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the session list once enabled; default the selection to the most recent
  // (listSessions returns newest-first) when none is chosen yet.
  useEffect(() => {
    if (!enabled || !accessToken) return;
    let ignore = false;
    void (async () => {
      try {
        const res = await chatApi.listSessions(accessToken);
        if (ignore) return;
        const items = Array.isArray(res?.items) ? res.items : [];
        setSessions(items);
        setSessionId((cur) => cur ?? items[0]?.session_id ?? null);
      } catch {
        /* the trace fetch below surfaces errors; a session-list miss just leaves
           the picker empty */
      }
    })();
    return () => {
      ignore = true;
    };
  }, [enabled, accessToken]);

  const load = useCallback(
    async (shouldApply: () => boolean = () => true) => {
      if (!accessToken || !sessionId) return;
      setLoading(true);
      setError(null);
      try {
        const res = await chatApi.getContextTrace(accessToken, sessionId);
        if (!shouldApply()) return;
        setPoints(Array.isArray(res?.items) ? res.items : []);
      } catch (err) {
        if (!shouldApply()) return;
        setError((err as Error)?.message ?? 'failed to load context trace');
        setPoints([]);
      } finally {
        if (shouldApply()) setLoading(false);
      }
    },
    [accessToken, sessionId],
  );

  // Clear stale turns the instant the selected session changes, so the view falls
  // back to its spinner/empty rather than showing the previous session's turns.
  useEffect(() => {
    setPoints([]);
  }, [sessionId]);

  // Fetch the trace when enabled + a session is selected (or either changes). The
  // ignore flag drops a stale resolution on a fast session switch.
  useEffect(() => {
    if (!enabled || !sessionId) return;
    let ignore = false;
    void load(() => !ignore);
    return () => {
      ignore = true;
    };
  }, [enabled, sessionId, load]);

  // Live update (spec §11a) — poll while the panel is enabled + a session is
  // selected, so a turn that finishes elsewhere appears without a manual refresh.
  // A modest interval (the trace endpoint is cheap + a session's turn count is
  // bounded); an SSE push upgrade is a tracked follow-up. Also refetch on window
  // focus so returning to the tab shows the latest immediately.
  useEffect(() => {
    if (!enabled || !sessionId) return;
    const tick = () => void load();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    window.addEventListener('focus', tick);
    return () => {
      clearInterval(id);
      window.removeEventListener('focus', tick);
    };
  }, [enabled, sessionId, load]);

  const selectSession = useCallback((id: string) => setSessionId(id), []);
  const reload = useCallback(() => void load(), [load]);

  return { sessions, sessionId, selectSession, points, loading, error, reload };
}

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatSession, CreateSessionPayload } from '../types';

export function useSessions() {
  const { accessToken } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await chatApi.listSessions(accessToken);
      setSessions(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createSession = useCallback(
    async (payload: CreateSessionPayload): Promise<ChatSession> => {
      if (!accessToken) throw new Error('Not authenticated');
      const session = await chatApi.createSession(accessToken, payload);
      setSessions((prev) => [session, ...prev]);
      return session;
    },
    [accessToken],
  );

  const renameSession = useCallback(
    async (sessionId: string, title: string) => {
      if (!accessToken) return;
      const updated = await chatApi.patchSession(accessToken, sessionId, { title });
      setSessions((prev) => prev.map((s) => (s.session_id === sessionId ? updated : s)));
    },
    [accessToken],
  );

  const archiveSession = useCallback(
    async (sessionId: string) => {
      if (!accessToken) return;
      await chatApi.patchSession(accessToken, sessionId, { status: 'archived' });
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    },
    [accessToken],
  );

  const deleteSession = useCallback(
    async (sessionId: string) => {
      if (!accessToken) return;
      await chatApi.deleteSession(accessToken, sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    },
    [accessToken],
  );

  return { sessions, loading, error, refresh, createSession, renameSession, archiveSession, deleteSession };
}

// T4d — session + model lifecycle controller for the admin chat (no JSX).
// Owns: the admin user's user-models, the active-session list, the selected
// session, and create. Uses the USER token (chat-service + model-registry are
// the admin USER's resources; admin authority is layered on top per-turn).
import { useCallback, useEffect, useState } from 'react';
import { adminChatApi } from '../api';
import type { ChatSession, UserModelOption } from '../types';

interface UseAdminSessions {
  models: UserModelOption[];
  sessions: ChatSession[];
  activeId: string | null;
  selectedModel: string | null;
  loading: boolean;
  error: string | null;
  setActiveId: (id: string | null) => void;
  setSelectedModel: (modelRef: string | null) => void;
  createSession: () => Promise<ChatSession | null>;
  refresh: () => Promise<void>;
}

export function useAdminSessions(userToken: string | null): UseAdminSessions {
  const [models, setModels] = useState<UserModelOption[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!userToken) return;
    setLoading(true);
    setError(null);
    try {
      const [m, s] = await Promise.all([
        adminChatApi.listUserModels(userToken),
        adminChatApi.listSessions(userToken),
      ]);
      const ms = m.items ?? [];
      setModels(ms);
      setSessions(s.items ?? []);
      // Default the model to the first favorite, else the first model.
      setSelectedModel((prev) => prev ?? ms.find((x) => x.is_favorite)?.user_model_id ?? ms[0]?.user_model_id ?? null);
      // Default the active session to the most recent, if any.
      setActiveId((prev) => prev ?? s.items?.[0]?.session_id ?? null);
    } catch (err) {
      setError((err as Error).message || 'Failed to load admin chat');
    } finally {
      setLoading(false);
    }
  }, [userToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createSession = useCallback(async () => {
    if (!userToken || !selectedModel) {
      setError('Pick a model first.');
      return null;
    }
    try {
      const session = await adminChatApi.createSession(userToken, selectedModel);
      setSessions((prev) => [session, ...prev]);
      setActiveId(session.session_id);
      return session;
    } catch (err) {
      setError((err as Error).message || 'Could not create a session.');
      return null;
    }
  }, [userToken, selectedModel]);

  return {
    models,
    sessions,
    activeId,
    selectedModel,
    loading,
    error,
    setActiveId,
    setSelectedModel,
    createSession,
    refresh,
  };
}

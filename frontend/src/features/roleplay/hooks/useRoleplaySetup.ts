// Controller for the persona picker: loads the scripts (personas) + the user's
// chat-capable models, holds the selection, and starts a practice session. No
// JSX — pure logic + state (React-MVC).

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { chatApi } from '@/features/chat/api';
import type { ChatSession } from '@/features/chat/types';
import { roleplayApi } from '../api';
import type { Script } from '../types';

export interface RoleplaySetup {
  scripts: Script[];
  models: UserModel[];
  loading: boolean;
  selectedScriptId: string | null;
  selectedModelId: string | null;
  selectScript: (id: string) => void;
  selectModel: (id: string) => void;
  starting: boolean;
  canStart: boolean;
  start: () => Promise<ChatSession | null>;
}

export function useRoleplaySetup(): RoleplaySetup {
  const { accessToken } = useAuth();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [models, setModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedScriptId, setSelectedScriptId] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      roleplayApi.listScripts(accessToken),
      aiModelsApi.listUserModels(accessToken, { capability: 'chat' }),
    ])
      .then(([scriptList, mdl]) => {
        if (cancelled) return;
        setScripts(scriptList);
        setModels(mdl.items);
        // Sensible defaults: first script, the favorite (or first) model.
        if (scriptList.length) setSelectedScriptId((cur) => cur ?? scriptList[0].script_id);
        if (mdl.items.length) {
          const fav = mdl.items.find((m) => m.is_favorite) ?? mdl.items[0];
          setSelectedModelId((cur) => cur ?? fav.user_model_id);
        }
      })
      .catch(() => {
        if (!cancelled) toast.error('Could not load roleplay personas or models.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const selectScript = useCallback((id: string) => setSelectedScriptId(id), []);
  const selectModel = useCallback((id: string) => setSelectedModelId(id), []);

  const canStart = Boolean(selectedScriptId && selectedModelId && !starting);

  const start = useCallback(async (): Promise<ChatSession | null> => {
    if (!accessToken || !selectedScriptId || !selectedModelId) return null;
    setStarting(true);
    try {
      // roleplay-service freezes the charter + creates the chat session,
      // returning its id; load the full ChatSession to hand to chat's
      // selectSession (the acting loop stays on /v1/chat, seed-anchored).
      const { session_id } = await roleplayApi.startScript(accessToken, selectedScriptId, {
        model_source: 'user_model',
        model_ref: selectedModelId,
      });
      return await chatApi.getSession(accessToken, session_id);
    } catch {
      toast.error('Could not start the practice session.');
      return null;
    } finally {
      setStarting(false);
    }
  }, [accessToken, selectedScriptId, selectedModelId]);

  return useMemo(
    () => ({
      scripts,
      models,
      loading,
      selectedScriptId,
      selectedModelId,
      selectScript,
      selectModel,
      starting,
      canStart,
      start,
    }),
    [scripts, models, loading, selectedScriptId, selectedModelId, selectScript, selectModel, starting, canStart, start],
  );
}

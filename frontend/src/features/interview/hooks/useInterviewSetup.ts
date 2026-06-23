// Controller for the persona picker: loads the templates (personas) + the
// user's chat-capable models, holds the selection, and starts a practice
// session. No JSX — pure logic + state (React-MVC).

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import type { ChatSession } from '@/features/chat/types';
import { interviewApi } from '../api';
import type { SessionTemplate } from '../types';

export interface InterviewSetup {
  templates: SessionTemplate[];
  models: UserModel[];
  loading: boolean;
  selectedTemplateId: string | null;
  selectedModelId: string | null;
  selectTemplate: (id: string) => void;
  selectModel: (id: string) => void;
  starting: boolean;
  canStart: boolean;
  start: () => Promise<ChatSession | null>;
}

export function useInterviewSetup(): InterviewSetup {
  const { accessToken } = useAuth();
  const [templates, setTemplates] = useState<SessionTemplate[]>([]);
  const [models, setModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      interviewApi.listTemplates(accessToken),
      aiModelsApi.listUserModels(accessToken, { capability: 'chat' }),
    ])
      .then(([tpl, mdl]) => {
        if (cancelled) return;
        setTemplates(tpl.items);
        setModels(mdl.items);
        // Sensible defaults: first template, the favorite (or first) model.
        if (tpl.items.length) setSelectedTemplateId((cur) => cur ?? tpl.items[0].template_id);
        if (mdl.items.length) {
          const fav = mdl.items.find((m) => m.is_favorite) ?? mdl.items[0];
          setSelectedModelId((cur) => cur ?? fav.user_model_id);
        }
      })
      .catch(() => {
        if (!cancelled) toast.error('Could not load interview personas or models.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const selectTemplate = useCallback((id: string) => setSelectedTemplateId(id), []);
  const selectModel = useCallback((id: string) => setSelectedModelId(id), []);

  const canStart = Boolean(selectedTemplateId && selectedModelId && !starting);

  const start = useCallback(async (): Promise<ChatSession | null> => {
    if (!accessToken || !selectedTemplateId || !selectedModelId) return null;
    setStarting(true);
    try {
      const session = await interviewApi.startPractice(accessToken, selectedTemplateId, {
        model_source: 'user_model',
        model_ref: selectedModelId,
      });
      return session;
    } catch {
      toast.error('Could not start the practice session.');
      return null;
    } finally {
      setStarting(false);
    }
  }, [accessToken, selectedTemplateId, selectedModelId]);

  return useMemo(
    () => ({
      templates,
      models,
      loading,
      selectedTemplateId,
      selectedModelId,
      selectTemplate,
      selectModel,
      starting,
      canStart,
      start,
    }),
    [templates, models, loading, selectedTemplateId, selectedModelId, selectTemplate, selectModel, starting, canStart, start],
  );
}

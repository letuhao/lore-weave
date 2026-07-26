// Chat & AI settings — API layer (spec §6). Mirrors features/chat/api.ts.
import { apiJson } from '@/api';
import type { AiPrefs, AiPrefsPatch, ChatCapabilities, EffectiveSettings } from './types';

export const aiSettingsApi = {
  /** Deploy-tier capability ceilings (D-WS4C-EFFECTIVE-VALUE). Process-global, so a
   *  consumer ANDs `deploy_allows` with its own user/project knob to show the honest
   *  effective value — otherwise a kill-switched capability toggles silently. */
  getCapabilities(token: string): Promise<ChatCapabilities> {
    return apiJson<ChatCapabilities>('/v1/chat/capabilities', { token });
  },

  /** The resolved cascade for a context. Studio-tool callers omit sessionId
   *  (Session tier skipped); a chat session passes both. */
  getEffective(
    token: string,
    params: { bookId?: string | null; sessionId?: string | null } = {},
  ): Promise<EffectiveSettings> {
    const qs = new URLSearchParams();
    if (params.bookId) qs.set('book_id', params.bookId);
    if (params.sessionId) qs.set('session_id', params.sessionId);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return apiJson<EffectiveSettings>(`/v1/chat/effective-settings${suffix}`, { token });
  },

  getPrefs(token: string): Promise<AiPrefs> {
    return apiJson<AiPrefs>('/v1/chat/ai-prefs', { token });
  },

  patchPrefs(token: string, patch: AiPrefsPatch, ifMatch?: number): Promise<AiPrefs> {
    return apiJson<AiPrefs>('/v1/chat/ai-prefs', {
      method: 'PATCH',
      token,
      body: JSON.stringify(patch),
      ...(ifMatch != null ? { headers: { 'If-Match': String(ifMatch) } } : {}),
    });
  },
};

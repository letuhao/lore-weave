// Interview-practice API layer — all calls ride the shared apiJson wrapper
// (relative /v1 → gateway). The backend lives in chat-service under /v1/chat
// (templates + the /evaluate scorecard); the gateway proxies /v1/chat/* whole.

import { apiJson } from '@/api';
import type { ChatSession } from '@/features/chat/types';
import type { EvaluateResponse, SessionTemplate, StartPracticePayload } from './types';

export const interviewApi = {
  // Personas = session templates. Merges System defaults + the user's own.
  listTemplates(token: string) {
    return apiJson<{ items: SessionTemplate[] }>('/v1/chat/templates', { token });
  },

  // Clone a template into a real chat session (seeds the frozen charter). Returns
  // the full ChatSession — hand it straight to chat's selectSession().
  startPractice(token: string, templateId: string, payload: StartPracticePayload) {
    return apiJson<ChatSession>(`/v1/chat/templates/${templateId}/start`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  // Score a finished (or partial) practice transcript → stored scorecard.
  evaluate(token: string, sessionId: string) {
    return apiJson<EvaluateResponse>(`/v1/chat/sessions/${sessionId}/evaluate`, {
      method: 'POST',
      token,
    });
  },
};

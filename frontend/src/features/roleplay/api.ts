// Roleplay practice API layer — all calls ride the shared apiJson wrapper
// (relative /v1 → gateway). Scripts + start live in roleplay-service under
// /v1/roleplay (Rust). The live turn loop (acting) + the /evaluate scorecard
// stay in chat-service under /v1/chat — reused unchanged.

import { apiJson } from '@/api';
import type { EvaluateResponse, Script, StartScriptPayload, StartScriptResponse } from './types';

export const roleplayApi = {
  // Personas = scripts. Returns System defaults merged with the user's own
  // (a bare array from roleplay-service).
  listScripts(token: string) {
    return apiJson<Script[]>('/v1/roleplay/scripts', { token });
  },

  // Freeze the charter + create a chat session carrying the seed. Returns just
  // the session_id; the caller loads the full ChatSession via chatApi.getSession.
  startScript(token: string, scriptId: string, payload: StartScriptPayload) {
    return apiJson<StartScriptResponse>(`/v1/roleplay/scripts/${scriptId}/start`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  // Score a finished (or partial) practice transcript → stored scorecard.
  // Debrief stays in chat-service M6 (/v1/chat) for v1.
  evaluate(token: string, sessionId: string) {
    return apiJson<EvaluateResponse>(`/v1/chat/sessions/${sessionId}/evaluate`, {
      method: 'POST',
      token,
    });
  },
};

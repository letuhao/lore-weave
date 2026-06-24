// T4d — API layer for the CMS admin chat panel.
//
// Two token kinds are in play (see auth.tsx):
//   - userToken (HS256)  → the chat-service stream bearer (get_current_user).
//   - adminToken (RS256) → rides X-Admin-Token (admin surface routing) AND is
//                          the Authorization bearer for /actions/admin/{confirm,preview}.
// The X-Admin-Token value is a bearer credential — never log it.
import { apiJson, apiBase } from '@/api';
import type { ChatMessage, ChatSession, ActionPreview, UserModelOption } from './types';

const base = apiBase;

export const adminChatApi = {
  // ── Models (the admin user's own user-models; needs the USER token) ──────────
  listUserModels(userToken: string) {
    return apiJson<{ items: UserModelOption[] }>(
      '/v1/model-registry/user-models?include_inactive=false',
      { token: userToken },
    );
  },

  // ── Sessions (chat-service via the BFF /v1/chat; USER token) ─────────────────
  listSessions(userToken: string) {
    return apiJson<{ items: ChatSession[]; next_cursor: string | null }>(
      '/v1/chat/sessions?status=active',
      { token: userToken },
    );
  },

  createSession(userToken: string, modelRef: string, title = 'Admin standards chat') {
    return apiJson<ChatSession>('/v1/chat/sessions', {
      method: 'POST',
      token: userToken,
      body: JSON.stringify({ model_source: 'user_model', model_ref: modelRef, title }),
    });
  },

  listMessages(userToken: string, sessionId: string) {
    return apiJson<{ items: ChatMessage[] }>(
      `/v1/chat/sessions/${sessionId}/messages`,
      { token: userToken },
    );
  },

  // ── Streaming endpoints (raw fetch; the hook reads the SSE body) ─────────────
  messagesUrl(sessionId: string) {
    return `${base()}/v1/chat/sessions/${sessionId}/messages`;
  },
  toolResultsUrl(sessionId: string) {
    return `${base()}/v1/chat/sessions/${sessionId}/tool-results`;
  },

  // ── System-tier confirm (RS256 admin Authorization; NOT the user /confirm) ───
  // The admin confirm endpoint is gated by requireAdminScope (RS256), so the
  // admin token is the Authorization bearer here — distinct from the user path.
  confirmAdminAction(confirmToken: string, adminToken: string) {
    return apiJson<unknown>('/v1/glossary/actions/admin/confirm', {
      method: 'POST',
      token: adminToken,
      body: JSON.stringify({ confirm_token: confirmToken }),
    });
  },

  previewAdminAction(confirmToken: string, adminToken: string) {
    return apiJson<ActionPreview>('/v1/glossary/actions/admin/preview', {
      method: 'POST',
      token: adminToken,
      body: JSON.stringify({ confirm_token: confirmToken }),
    });
  },
};

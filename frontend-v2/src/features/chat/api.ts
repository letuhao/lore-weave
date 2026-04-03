// ── Chat V2 API Client ────────────────────────────────────────────────────────
// Uses the shared apiJson wrapper from @/api.

import { apiJson } from '@/api';
import type {
  ChatMessage,
  ChatOutput,
  ChatSession,
  CreateSessionPayload,
  PatchSessionPayload,
} from './types';

const base = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

export const chatApi = {
  // ── Sessions ──────────────────────────────────────────────────────────────────

  listSessions(token: string, status = 'active') {
    return apiJson<{ items: ChatSession[]; next_cursor: string | null }>(
      `/v1/chat/sessions?status=${status}`,
      { token },
    );
  },

  createSession(token: string, payload: CreateSessionPayload) {
    return apiJson<ChatSession>('/v1/chat/sessions', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  getSession(token: string, sessionId: string) {
    return apiJson<ChatSession>(`/v1/chat/sessions/${sessionId}`, { token });
  },

  patchSession(token: string, sessionId: string, payload: PatchSessionPayload) {
    return apiJson<ChatSession>(`/v1/chat/sessions/${sessionId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },

  deleteSession(token: string, sessionId: string) {
    return apiJson<void>(`/v1/chat/sessions/${sessionId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── Messages ──────────────────────────────────────────────────────────────────

  listMessages(token: string, sessionId: string, beforeSeq?: number) {
    const qs = beforeSeq != null ? `?before_seq=${beforeSeq}` : '';
    return apiJson<{ items: ChatMessage[] }>(
      `/v1/chat/sessions/${sessionId}/messages${qs}`,
      { token },
    );
  },

  // ── Outputs ───────────────────────────────────────────────────────────────────

  listOutputs(token: string, sessionId: string) {
    return apiJson<{ items: ChatOutput[] }>(
      `/v1/chat/sessions/${sessionId}/outputs`,
      { token },
    );
  },

  // ── URLs (open in browser) ────────────────────────────────────────────────────

  exportUrl(sessionId: string, format: 'markdown' | 'json' = 'markdown') {
    return `${base()}/v1/chat/sessions/${sessionId}/export?format=${format}`;
  },

  downloadUrl(outputId: string) {
    return `${base()}/v1/chat/outputs/${outputId}/download`;
  },

  // ── Branches ─────────────────────────────────────────────────────────────────

  listBranches(token: string, sessionId: string, sequenceNum: number) {
    return apiJson<{
      sequence_num: number;
      branches: Array<{ branch_id: number; message_count: number; created_at: string | null }>;
    }>(`/v1/chat/sessions/${sessionId}/branches?sequence_num=${sequenceNum}`, { token });
  },

  // ── Search ───────────────────────────────────────────────────────────────────

  searchMessages(token: string, query: string, limit = 20) {
    return apiJson<{
      items: Array<{
        session_id: string;
        session_title: string;
        message_id: string;
        role: string;
        snippet: string;
        created_at: string;
      }>;
    }>(`/v1/chat/sessions/search?q=${encodeURIComponent(query)}&limit=${limit}`, { token });
  },

  // ── Streaming endpoint base URL ───────────────────────────────────────────────

  messagesUrl(sessionId: string) {
    return `${base()}/v1/chat/sessions/${sessionId}/messages`;
  },
};

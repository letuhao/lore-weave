// ── Chat V2 API Client ────────────────────────────────────────────────────────
// Uses the shared apiJson wrapper from @/api.

import { apiJson, apiBase } from '@/api';
import type {
  ChatMessage,
  ChatOutput,
  ChatSession,
  CompactSessionResult,
  ContextBudget,
  ContextHistoryPoint,
  CreateSessionPayload,
  PatchSessionPayload,
  PendingFact,
} from './types';

// Shared base from @/api (relative '' by default → rides the same proxy→gateway
// path as apiJson). Used for SSE/streaming callers that bypass apiJson.
const base = apiBase;

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

  // W3 — manual steerable compact: summarize everything but the recent turns
  // with the session's own model and PERSIST it on the session (multi-device).
  // `instructions` steer what must survive ("keep all plot promises and
  // character names"); omit for the default synopsis. `{clear: true}` wipes
  // the stored compact instead (mutually exclusive with the other fields).
  compactSession(
    token: string,
    sessionId: string,
    payload: { instructions?: string; keep_recent?: number; clear?: boolean } = {},
  ) {
    return apiJson<CompactSessionResult>(`/v1/chat/sessions/${sessionId}/compact`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  // ── Messages ──────────────────────────────────────────────────────────────────

  listMessages(token: string, sessionId: string, beforeSeq?: number, branchId?: number) {
    const params = new URLSearchParams();
    if (beforeSeq != null) params.set('before_seq', String(beforeSeq));
    if (branchId != null && branchId > 0) params.set('branch_id', String(branchId));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return apiJson<{ items: ChatMessage[] }>(
      `/v1/chat/sessions/${sessionId}/messages${qs}`,
      { token },
    );
  },

  // W1-residual — the per-turn context-token HISTORY series (how each category's
  // token cost evolved across the session's assistant turns). Backed by the
  // W1-persisted chat_messages.context_breakdown; owner-gated server-side.
  getContextHistory(token: string, sessionId: string, limit?: number) {
    const qs = limit != null ? `?limit=${limit}` : '';
    return apiJson<{ items: ContextHistoryPoint[] }>(
      `/v1/chat/sessions/${sessionId}/context-history${qs}`,
      { token },
    );
  },

  // The LAST assistant turn's persisted contextBudget frame — lets the header
  // meter SEED on session load instead of only appearing after the next live
  // turn finishes. `budget` is null for a brand-new session with no measured turn.
  getLatestContextBudget(token: string, sessionId: string) {
    return apiJson<{ budget: ContextBudget | null }>(
      `/v1/chat/sessions/${sessionId}/context-budget`,
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

  deleteMessage(token: string, sessionId: string, messageId: string) {
    return apiJson<void>(`/v1/chat/sessions/${sessionId}/messages/${messageId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── Feedback (Production Eval + Feedback Flywheel, Q3) ─────────────────────────
  // Explicit thumbs (+1/-1) or implicit regenerate-as-negative on an assistant
  // turn. Server is the source of truth (the rating is persisted + flows to the
  // learning-service quality plane); the UI keeps only ephemeral highlight state.

  submitMessageFeedback(
    token: string,
    messageId: string,
    payload: { rating: 1 | -1; reason?: string; regenerated_from_message_id?: string },
  ) {
    return apiJson<{ id: string; message_id: string; rating: number; created_at: string }>(
      `/v1/chat/messages/${messageId}/feedback`,
      { method: 'POST', token, body: JSON.stringify(payload) },
    );
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

  // ── K21-C (D7/D8): pending-facts review ───────────────────────────────────────
  // Served by knowledge-service through the gateway, so the path is
  // /v1/knowledge/... not /v1/chat/... — same apiJson base. The chat
  // feature owns these calls because the FE surfaces queued facts
  // below the chat (PendingFactsCard).

  listPendingFacts(token: string, sessionId: string) {
    return apiJson<PendingFact[]>(
      `/v1/knowledge/pending-facts?session_id=${encodeURIComponent(sessionId)}`,
      { token },
    );
  },

  // Returns the created `:Fact` (200). The FE doesn't render the body —
  // a confirm just refetches the list — so the return is typed loosely.
  confirmPendingFact(token: string, pendingFactId: string) {
    return apiJson<unknown>(
      `/v1/knowledge/pending-facts/${encodeURIComponent(pendingFactId)}/confirm`,
      { method: 'POST', token },
    );
  },

  // BE returns 204 No Content — apiJson resolves undefined.
  rejectPendingFact(token: string, pendingFactId: string) {
    return apiJson<void>(
      `/v1/knowledge/pending-facts/${encodeURIComponent(pendingFactId)}/reject`,
      { method: 'POST', token },
    );
  },

  // ── Streaming endpoint base URL ───────────────────────────────────────────────

  messagesUrl(sessionId: string) {
    return `${base()}/v1/chat/sessions/${sessionId}/messages`;
  },

  // ARCH-1 C6: resume endpoint — the FE POSTs a frontend-tool result here
  // (the user's apply/dismiss of a proposed edit) to continue the agent's run.
  toolResultsUrl(sessionId: string) {
    return `${base()}/v1/chat/sessions/${sessionId}/tool-results`;
  },

  listToolsCatalog(token: string) {
    return apiJson<{ items: import('./types').ToolCatalogItem[] }>(
      '/v1/chat/tools/catalog',
      { token },
    );
  },

  listSkillsCatalog(token: string) {
    return apiJson<{ items: import('./types').SkillCatalogItem[] }>(
      '/v1/chat/skills/catalog',
      { token },
    );
  },
};

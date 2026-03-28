import type {
  ChatOutput,
  ChatSession,
  CreateSessionPayload,
  PatchSessionPayload,
} from './types';

const base = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

async function req<T>(
  method: string,
  path: string,
  token: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export const chatApi = {
  createSession: (token: string, payload: CreateSessionPayload) =>
    req<ChatSession>('POST', '/v1/chat/sessions', token, payload),

  listSessions: (token: string, status = 'active') =>
    req<{ items: ChatSession[]; next_cursor: string | null }>(
      'GET',
      `/v1/chat/sessions?status=${status}`,
      token,
    ),

  getSession: (token: string, sessionId: string) =>
    req<ChatSession>('GET', `/v1/chat/sessions/${sessionId}`, token),

  patchSession: (token: string, sessionId: string, payload: PatchSessionPayload) =>
    req<ChatSession>('PATCH', `/v1/chat/sessions/${sessionId}`, token, payload),

  deleteSession: (token: string, sessionId: string) =>
    req<void>('DELETE', `/v1/chat/sessions/${sessionId}`, token),

  // ── Messages ────────────────────────────────────────────────────────────────

  listMessages: (token: string, sessionId: string) =>
    req<{ items: import('./types').ChatMessage[] }>(
      'GET',
      `/v1/chat/sessions/${sessionId}/messages`,
      token,
    ),

  // ── Outputs ─────────────────────────────────────────────────────────────────

  listOutputs: (token: string, sessionId: string) =>
    req<{ items: ChatOutput[] }>(
      'GET',
      `/v1/chat/sessions/${sessionId}/outputs`,
      token,
    ),

  getOutput: (token: string, outputId: string) =>
    req<ChatOutput>('GET', `/v1/chat/outputs/${outputId}`, token),

  patchOutput: (token: string, outputId: string, title: string) =>
    req<ChatOutput>('PATCH', `/v1/chat/outputs/${outputId}`, token, { title }),

  deleteOutput: (token: string, outputId: string) =>
    req<void>('DELETE', `/v1/chat/outputs/${outputId}`, token),

  downloadUrl: (outputId: string) =>
    `${base()}/v1/chat/outputs/${outputId}/download`,

  exportUrl: (sessionId: string, format: 'markdown' | 'json' = 'markdown') =>
    `${base()}/v1/chat/sessions/${sessionId}/export?format=${format}`,
};

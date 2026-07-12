// WS-1.10 — the Work Assistant API layer. Assistant-specific control-plane calls; entity/chapter
// reads reuse glossaryApi / chatApi from their own features (no duplication).
import { apiJson } from '@/api';
import type { DiaryEntriesResponse, EndDayResult, ProvisionResult } from './types';

export interface EndDayPayload {
  book_id: string;
  model_source: string;
  model_ref: string;
  language?: string;
  entry_zone?: string;
}

export const assistantApi = {
  /** Idempotent get-or-create of the diary book + assistant project + work ontology + self-entity.
   *  Safe to re-drive on every home open (the BFF's steps are all idempotent). */
  provision(token: string, title?: string) {
    return apiJson<ProvisionResult>('/v1/assistant/provision', {
      method: 'POST',
      token,
      body: JSON.stringify({ title }),
    });
  },

  /** A2 — the per-turn work-capture CONSENT toggle (fail-closed default false, D-R17). */
  setCaptureConsent(token: string, projectId: string, enabled: boolean) {
    return apiJson<{ project_id: string; canon_capture_enabled: boolean }>(
      `/v1/knowledge/projects/${projectId}/capture-consent`,
      { method: 'PUT', token, body: JSON.stringify({ enabled }) },
    );
  },

  /** A1 — "End my day": enqueue the distiller. entry_date is server-authoritative (never sent). */
  endDay(token: string, payload: EndDayPayload) {
    return apiJson<EndDayResult>('/v1/assistant/end-day', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  /** Owner-only diary entries (newest-first, body inline) for the timeline + review. */
  listDiaryEntries(token: string, bookId: string) {
    return apiJson<DiaryEntriesResponse>(`/v1/books/${bookId}/diary/entries`, { token });
  },

  /** B2 — REVIEW→KEEP a draft entry (sets diary_kept_at; a re-distill won't clobber it). */
  keepDiaryEntry(token: string, bookId: string, chapterId: string) {
    return apiJson<{ chapter_id: string; kept: boolean; diary_kept_at: string }>(
      `/v1/books/${bookId}/diary/entries/${chapterId}/keep`,
      { method: 'POST', token },
    );
  },
};

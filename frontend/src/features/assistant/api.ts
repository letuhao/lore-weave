// WS-1.10 — the Work Assistant API layer. Assistant-specific control-plane calls; entity/chapter
// reads reuse glossaryApi / chatApi from their own features (no duplication).
import { apiJson } from '@/api';
import type {
  CorrectResult,
  DiaryEntriesResponse,
  DiaryPendingFact,
  EndDayResult,
  ForgetResult,
  ProvisionResult,
  ReflectionPattern,
  ScorecardItem,
} from './types';

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

  /** WS-2.6a / D17 — CORRECT a memory: the user edits a diary day's distilled entry text. One call, two
   *  legs behind it — the BFF amends the PG entry (SSOT), then enqueues the graph reconcile (re-extract +
   *  invalidate the day's superseded facts). No publish/share/collaborators — owner-gated server-side. The
   *  re-extract model rides `model_source`/`model_ref` (the caller's chosen chat model, per end-day). */
  correctDiaryEntry(
    token: string,
    payload: {
      book_id: string;
      chapter_id: string;
      body: string;
      title?: string;
      model_source: string;
      model_ref: string;
      language?: string;
    },
  ) {
    return apiJson<CorrectResult>('/v1/assistant/correct', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  /** WS-2.6c / D17 — FORGET a person: the scoped-erasure primitive. One call deletes the STRUCTURED memory
   *  (KG entity + facts + pending tombstone) AND redacts the name from the diary source prose. Irreversible;
   *  keyed by the remembered person's `name`. Owner-gated server-side (JWT sub); scoped to the diary book. */
  forgetPerson(token: string, payload: { book_id: string; name: string }) {
    return apiJson<ForgetResult>('/v1/assistant/forget', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  /** WS-2.5 — the diary FACT inbox: the caller's DIARY (session-less) pending facts, oldest-first.
   *  `diary_only=true` is load-bearing: a bare list returns ALL pending facts, so chat-memory facts
   *  from other projects would leak into this inbox (audit MED). JWT-scoped to the caller. */
  listDiaryFacts(token: string) {
    return apiJson<DiaryPendingFact[]>('/v1/knowledge/pending-facts?diary_only=true', { token });
  },

  /** WS-2.5 — CONFIRM a pending diary fact → promoted to the KG (dated, subject-linked, recallable). */
  confirmDiaryFact(token: string, pendingFactId: string) {
    return apiJson<unknown>(
      `/v1/knowledge/pending-facts/${encodeURIComponent(pendingFactId)}/confirm`,
      { method: 'POST', token },
    );
  },

  /** WS-2.5 — REJECT a pending diary fact → deleted + tombstoned (not re-proposed next distill). */
  rejectDiaryFact(token: string, pendingFactId: string) {
    return apiJson<void>(
      `/v1/knowledge/pending-facts/${encodeURIComponent(pendingFactId)}/reject`,
      { method: 'POST', token },
    );
  },

  /** C8 / WS-5.6 — DISMISS a weekly-reflection pattern permanently. The BFF derives the owner from the
   *  JWT; worker-ai then drops that pattern_key AT DETECTION so it never resurfaces (C2 tombstone). */
  dismissReflectionPattern(token: string, patternKey: string) {
    return apiJson<{ dismissed: boolean; pattern_key: string }>('/v1/assistant/reflection-dismiss', {
      method: 'POST',
      token,
      body: JSON.stringify({ pattern_key: patternKey }),
    });
  },

  /** R2 (D-COACHING-SCORECARD-MOUNT) — the user's persisted coaching scorecards (newest-first). Each
   *  card carries `quarantine` (SD-7); the FE shows it with a badge and NEVER trends a quarantine score. */
  getScorecards(token: string) {
    return apiJson<{ scorecards: ScorecardItem[] }>('/v1/assistant/scorecards', { token });
  },

  /** R1 (D-REFLECTION-PATTERNS-FEED) — the DISMISSABLE reflection patterns for a given week (server
   *  already excludes the user's tombstoned ones). `weekEnd` MUST be the displayed draft's week so the
   *  chips correspond to the shown draft — a CALM week correctly returns no chips (never a stale prior
   *  week's set). Feeds the ReflectionCard's chips. Server is SoT. */
  getReflectionPatterns(token: string, weekEnd?: string) {
    const q = weekEnd ? `?week_end=${encodeURIComponent(weekEnd)}` : '';
    return apiJson<{ week_end: string | null; patterns: ReflectionPattern[] }>(
      `/v1/assistant/reflection-patterns${q}`,
      { token },
    );
  },
};

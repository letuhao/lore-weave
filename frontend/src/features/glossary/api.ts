import { apiJson } from '@/api';
import type {
  EntityKind,
  GlossaryEntity,
  GlossaryEntityListResponse,
  FilterState,
  Relevance,
  Confidence,
} from './types';

const BASE = '/v1/glossary';

// ── Kinds ─────────────────────────────────────────────────────────────────────

export const glossaryApi = {
  /** GET /v1/glossary/kinds */
  getKinds(token: string): Promise<EntityKind[]> {
    return apiJson<EntityKind[]>(`${BASE}/kinds`, { token });
  },

  // ── Entities ────────────────────────────────────────────────────────────────

  /** GET /v1/glossary/books/{bookId}/entities */
  listEntities(
    bookId: string,
    filters: FilterState & { limit?: number; offset?: number; sort?: string },
    token: string,
  ): Promise<GlossaryEntityListResponse> {
    const params = new URLSearchParams();
    if (filters.kindCodes.length > 0) params.set('kind_codes', filters.kindCodes.join(','));
    if (filters.status !== 'all') params.set('status', filters.status);
    if (Array.isArray(filters.chapterIds) && filters.chapterIds.length > 0) {
      params.set('chapter_ids', filters.chapterIds.join(','));
    } else if (filters.chapterIds === 'unlinked') {
      params.set('chapter_ids', 'unlinked');
    }
    if (filters.searchQuery) params.set('search', filters.searchQuery);
    if (filters.tags.length > 0) params.set('tags', filters.tags.join(','));
    if (filters.limit) params.set('limit', String(filters.limit));
    if (filters.offset) params.set('offset', String(filters.offset));
    if (filters.sort) params.set('sort', filters.sort);
    const qs = params.toString();
    return apiJson<GlossaryEntityListResponse>(
      `${BASE}/books/${bookId}/entities${qs ? '?' + qs : ''}`,
      { token },
    );
  },

  /** POST /v1/glossary/books/{bookId}/entities */
  createEntity(bookId: string, kindId: string, token: string): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities`, {
      method: 'POST',
      body: JSON.stringify({ kind_id: kindId }),
      token,
    });
  },

  /** GET /v1/glossary/books/{bookId}/entities/{entityId} */
  getEntity(bookId: string, entityId: string, token: string): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities/${entityId}`, { token });
  },

  /** PATCH /v1/glossary/books/{bookId}/entities/{entityId} */
  patchEntity(
    bookId: string,
    entityId: string,
    changes: { status?: string; tags?: string[] },
    token: string,
  ): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities/${entityId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  /** DELETE /v1/glossary/books/{bookId}/entities/{entityId} */
  deleteEntity(bookId: string, entityId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/entities/${entityId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── Chapter Links (SP-3) ────────────────────────────────────────────────────

  createChapterLink(
    bookId: string,
    entityId: string,
    body: { chapter_id: string; relevance: Relevance; note?: string },
    token: string,
  ) {
    return apiJson(`${BASE}/books/${bookId}/entities/${entityId}/chapter-links`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  patchChapterLink(
    bookId: string,
    entityId: string,
    linkId: string,
    changes: { relevance?: Relevance; note?: string },
    token: string,
  ) {
    return apiJson(
      `${BASE}/books/${bookId}/entities/${entityId}/chapter-links/${linkId}`,
      { method: 'PATCH', body: JSON.stringify(changes), token },
    );
  },

  deleteChapterLink(bookId: string, entityId: string, linkId: string, token: string) {
    return apiJson<void>(
      `${BASE}/books/${bookId}/entities/${entityId}/chapter-links/${linkId}`,
      { method: 'DELETE', token },
    );
  },

  // ── Attribute Values (SP-4) ─────────────────────────────────────────────────

  patchAttributeValue(
    bookId: string,
    entityId: string,
    attrValueId: string,
    changes: { original_language?: string; original_value?: string },
    token: string,
  ) {
    return apiJson(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}`,
      { method: 'PATCH', body: JSON.stringify(changes), token },
    );
  },

  // ── Translations (SP-4) ─────────────────────────────────────────────────────

  createTranslation(
    bookId: string,
    entityId: string,
    attrValueId: string,
    body: { language_code: string; value: string; confidence: Confidence; translator?: string },
    token: string,
  ) {
    return apiJson(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
  },

  deleteTranslation(
    bookId: string,
    entityId: string,
    attrValueId: string,
    translationId: string,
    token: string,
  ) {
    return apiJson<void>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/translations/${translationId}`,
      { method: 'DELETE', token },
    );
  },

  // ── Evidences (SP-5) ────────────────────────────────────────────────────────

  createEvidence(
    bookId: string,
    entityId: string,
    attrValueId: string,
    body: object,
    token: string,
  ) {
    return apiJson(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
  },

  deleteEvidence(
    bookId: string,
    entityId: string,
    attrValueId: string,
    evidenceId: string,
    token: string,
  ) {
    return apiJson<void>(
      `${BASE}/books/${bookId}/entities/${entityId}/attributes/${attrValueId}/evidences/${evidenceId}`,
      { method: 'DELETE', token },
    );
  },

  // ── Export (SP-5) ───────────────────────────────────────────────────────────

  exportGlossary(bookId: string, token: string, chapterId?: string) {
    const qs = chapterId ? `?chapter_id=${chapterId}` : '';
    return apiJson<object>(`${BASE}/books/${bookId}/export${qs}`, { token });
  },
};

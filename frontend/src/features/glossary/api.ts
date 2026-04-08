import { apiJson } from '../../api';
import type {
  EntityKind,
  EntityNameEntry,
  GenreGroup,
  GlossaryEntity,
  GlossaryEntityListResponse,
  FilterState,
} from './types';

const BASE = '/v1/glossary';

export const glossaryApi = {
  getKinds(token: string): Promise<EntityKind[]> {
    return apiJson<EntityKind[]>(`${BASE}/kinds`, { token });
  },

  listEntities(
    bookId: string,
    filters: FilterState & { limit?: number; offset?: number; sort?: string },
    token: string,
  ): Promise<GlossaryEntityListResponse> {
    const params = new URLSearchParams();
    if (filters.kindCodes.length > 0) params.set('kind_codes', filters.kindCodes.join(','));
    if (filters.status !== 'all') params.set('status', filters.status);
    if (filters.searchQuery) params.set('search', filters.searchQuery);
    if (filters.limit) params.set('limit', String(filters.limit));
    if (filters.offset) params.set('offset', String(filters.offset));
    if (filters.sort) params.set('sort', filters.sort);
    const qs = params.toString();
    return apiJson<GlossaryEntityListResponse>(
      `${BASE}/books/${bookId}/entities${qs ? '?' + qs : ''}`,
      { token },
    );
  },

  createEntity(bookId: string, kindId: string, token: string): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities`, {
      method: 'POST',
      body: JSON.stringify({ kind_id: kindId }),
      token,
    });
  },

  getEntity(bookId: string, entityId: string, token: string): Promise<GlossaryEntity> {
    return apiJson<GlossaryEntity>(`${BASE}/books/${bookId}/entities/${entityId}`, { token });
  },

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

  /** Lightweight names-only list for editor decoration scanning */
  listEntityNames(bookId: string, token: string): Promise<EntityNameEntry[]> {
    return apiJson<EntityNameEntry[]>(`${BASE}/books/${bookId}/entity-names`, { token });
  },

  deleteEntity(bookId: string, entityId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/entities/${entityId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── Kind CRUD ──────────────────────────────────────────────────────────────

  createKind(token: string, payload: { code: string; name: string; icon?: string; color?: string; genre_tags?: string[] }) {
    return apiJson<import('./types').EntityKind>(`${BASE}/kinds`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  patchKind(token: string, kindId: string, changes: Record<string, unknown>) {
    return apiJson<import('./types').EntityKind>(`${BASE}/kinds/${kindId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  deleteKind(token: string, kindId: string): Promise<void> {
    return apiJson<void>(`${BASE}/kinds/${kindId}`, { method: 'DELETE', token });
  },

  reorderKinds(token: string, kindIds: string[]) {
    return apiJson<{ reordered: number }>(`${BASE}/kinds/reorder`, {
      method: 'PATCH',
      body: JSON.stringify({ kind_ids: kindIds }),
      token,
    });
  },

  reorderAttrDefs(token: string, kindId: string, attrDefIds: string[]) {
    return apiJson<{ reordered: number }>(`${BASE}/kinds/${kindId}/attributes/reorder`, {
      method: 'PATCH',
      body: JSON.stringify({ attr_def_ids: attrDefIds }),
      token,
    });
  },

  // ── Attribute Definition CRUD ─────────────────────────────────────────────

  createAttrDef(token: string, kindId: string, payload: {
    code: string; name: string; description?: string; field_type?: string; is_required?: boolean;
    sort_order?: number; options?: string[]; genre_tags?: string[];
    auto_fill_prompt?: string; translation_hint?: string;
  }) {
    return apiJson<import('./types').AttributeDefinition>(`${BASE}/kinds/${kindId}/attributes`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  patchAttrDef(token: string, kindId: string, attrDefId: string, changes: Record<string, unknown>) {
    return apiJson<import('./types').AttributeDefinition>(`${BASE}/kinds/${kindId}/attributes/${attrDefId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  deleteAttrDef(token: string, kindId: string, attrDefId: string): Promise<void> {
    return apiJson<void>(`${BASE}/kinds/${kindId}/attributes/${attrDefId}`, { method: 'DELETE', token });
  },

  // ── Attribute Values ──────────────────────────────────────────────────────

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

  // ── Genre Groups ────────────────────────────────────────────────────────────

  listGenres(bookId: string, token: string): Promise<GenreGroup[]> {
    return apiJson<GenreGroup[]>(`${BASE}/books/${bookId}/genres`, { token });
  },

  createGenre(
    bookId: string,
    payload: { name: string; color?: string; description?: string; sort_order?: number },
    token: string,
  ): Promise<GenreGroup> {
    return apiJson<GenreGroup>(`${BASE}/books/${bookId}/genres`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  patchGenre(
    bookId: string,
    genreId: string,
    changes: Record<string, unknown>,
    token: string,
  ): Promise<GenreGroup> {
    return apiJson<GenreGroup>(`${BASE}/books/${bookId}/genres/${genreId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
      token,
    });
  },

  deleteGenre(bookId: string, genreId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/genres/${genreId}`, {
      method: 'DELETE',
      token,
    });
  },
};

import { apiJson } from '../../api';
import type {
  EntityKind,
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

  deleteEntity(bookId: string, entityId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/entities/${entityId}`, {
      method: 'DELETE',
      token,
    });
  },

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
};

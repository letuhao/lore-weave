import { apiJson } from '@/api';
import type { RawSearchParams, RawSearchResponse } from './types';

// Lexical leg lives on book-service (gateway proxies /v1/books/* → book-service).
// Phase 2 adds a semantic/hybrid endpoint on /v1/knowledge/books/{id}/search.
export const rawSearchApi = {
  search(
    bookId: string,
    params: RawSearchParams,
    token: string,
  ): Promise<RawSearchResponse> {
    const qs = new URLSearchParams();
    qs.set('q', params.q);
    if (params.surface) qs.set('surface', params.surface);
    if (params.limit != null) qs.set('limit', String(params.limit));
    return apiJson<RawSearchResponse>(
      `/v1/books/${bookId}/search?${qs.toString()}`,
      { token },
    );
  },
};

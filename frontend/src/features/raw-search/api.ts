import { apiJson } from '@/api';
import type { RawSearchParams, RawSearchResponse } from './types';

// Lexical leg → book-service (always available, draft surface).
function lexicalSearch(
  bookId: string,
  params: RawSearchParams,
  token: string,
): Promise<RawSearchResponse> {
  const qs = new URLSearchParams();
  qs.set('q', params.q);
  if (params.surface) qs.set('surface', params.surface);
  if (params.limit != null) qs.set('limit', String(params.limit));
  if (params.granularity) qs.set('granularity', params.granularity);
  return apiJson<RawSearchResponse>(
    `/v1/books/${bookId}/search?${qs.toString()}`,
    { token },
  );
}

// Hybrid/semantic leg → knowledge orchestrator (lexical+semantic RRF).
// Falls back to the book-service lexical endpoint on 404 (book not indexed /
// no knowledge project) or 503 (knowledge-service down) so raw search keeps
// working when the semantic stack is unavailable (spec §3.5). Other errors
// propagate so the panel can surface them.
async function hybridSearch(
  bookId: string,
  params: RawSearchParams,
  token: string,
): Promise<RawSearchResponse> {
  const qs = new URLSearchParams();
  qs.set('query', params.q); // knowledge endpoint param is `query`
  qs.set('mode', params.mode ?? 'hybrid');
  if (params.limit != null) qs.set('limit', String(params.limit));
  if (params.granularity) qs.set('granularity', params.granularity);
  // Only send rerank when disabling it (Mine) — backend default is on.
  if (params.rerank === false) qs.set('rerank', 'false');
  try {
    return await apiJson<RawSearchResponse>(
      `/v1/knowledge/books/${bookId}/search?${qs.toString()}`,
      { token },
    );
  } catch (e) {
    const stat = (e as { status?: number }).status;
    // Fall back to the always-available lexical leg when the knowledge route is
    // unavailable: 404 (no project / not_indexed) or any 5xx (knowledge-service
    // or gateway failure — the gateway emits 503 on ECONNREFUSED, 502/504 on
    // upstream errors/timeouts). Other 4xx (auth/validation) propagate.
    if (stat === 404 || (stat != null && stat >= 500)) {
      const fallback = await lexicalSearch(
        bookId,
        { q: params.q, limit: params.limit, granularity: params.granularity },
        token,
      );
      // Tell the UI the semantic leg was skipped (AC5 transparency).
      return { ...fallback, degraded: { ...fallback.degraded, semantic: 'unavailable' } };
    }
    throw e;
  }
}

export const rawSearchApi = {
  search: lexicalSearch,
  searchHybrid: hybridSearch,
};

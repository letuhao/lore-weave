import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { rawSearchApi } from '../api';
import type { RawSearchHit } from '../types';

// Raw-search hook. queryKey is userId-prefixed (cross-tenant flash guard).
// MIN length 1 (ADJ-2 — short CJK terms); the panel debounces input so this
// isn't per-keystroke. retry:false — a search error is shown, not retried.
// mode "hybrid" (default) hits the knowledge orchestrator (semantic+lexical,
// RRF) and auto-falls-back to the book-service lexical endpoint on 404/503;
// mode "lexical" hits book-service directly (always available).

export const RAW_SEARCH_MIN_QUERY_LENGTH = 1;
const DEFAULT_LIMIT = 20;

export type RawSearchMode = 'lexical' | 'hybrid';
/** chapter = best block per chapter (Navigate); block = every match (Mine). */
export type RawSearchGranularity = 'chapter' | 'block';

export interface UseRawSearchOptions {
  mode?: RawSearchMode;
  limit?: number;
  granularity?: RawSearchGranularity;
}

export interface UseRawSearchResult {
  hits: RawSearchHit[];
  /** True until a meaningful query is typed — render a hint, not "no results". */
  disabled: boolean;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  /** Per-leg degradation note from the hybrid endpoint (empty for lexical). */
  degraded: Record<string, string>;
}

export function useRawSearch(
  bookId: string,
  query: string,
  opts: UseRawSearchOptions = {},
): UseRawSearchResult {
  const { mode = 'hybrid', limit = DEFAULT_LIMIT, granularity = 'chapter' } = opts;
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const q = query.trim();
  const active = !!bookId && q.length >= RAW_SEARCH_MIN_QUERY_LENGTH;

  // Mine (block) ⇒ rerank off, so it stays exhaustive (the rerank score-floor
  // would prune matches); Navigate (chapter) keeps rerank for precision.
  const rerank = granularity !== 'block';

  const result = useQuery({
    queryKey: ['raw-search', userId, bookId, mode, q, limit, granularity] as const,
    queryFn: () =>
      mode === 'lexical'
        ? rawSearchApi.search(bookId, { q, limit, granularity }, accessToken!)
        : rawSearchApi.searchHybrid(
            bookId, { q, mode: 'hybrid', limit, granularity, rerank }, accessToken!,
          ),
    enabled: !!accessToken && active,
    retry: false,
    staleTime: 30_000,
  });

  return {
    hits: result.data?.results ?? [],
    disabled: !active,
    isLoading: result.isLoading,
    isFetching: result.isFetching,
    error: (result.error as Error | null) ?? null,
    degraded: result.data?.degraded ?? {},
  };
}

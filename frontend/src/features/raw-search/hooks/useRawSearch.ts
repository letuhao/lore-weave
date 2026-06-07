import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { rawSearchApi } from '../api';
import type { RawSearchHit } from '../types';

// Lexical raw-search hook. queryKey is userId-prefixed (cross-tenant flash
// guard on the shared QueryClient logout→login). MIN length is 1 (ADJ-2 —
// short CJK term hunting is a primary use); the lexical leg is cheap (no
// embedding), so per-keystroke querying gated only by min-length + staleTime
// is acceptable. retry:false — a search error is shown, not silently retried.

export const RAW_SEARCH_MIN_QUERY_LENGTH = 1;
const DEFAULT_LIMIT = 20;

export interface UseRawSearchResult {
  hits: RawSearchHit[];
  /** True until a meaningful query is typed — render a hint, not "no results". */
  disabled: boolean;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
}

export function useRawSearch(
  bookId: string,
  query: string,
  limit: number = DEFAULT_LIMIT,
): UseRawSearchResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const q = query.trim();
  const active = !!bookId && q.length >= RAW_SEARCH_MIN_QUERY_LENGTH;

  const result = useQuery({
    queryKey: ['raw-search', userId, bookId, q, limit] as const,
    queryFn: () => rawSearchApi.search(bookId, { q, limit }, accessToken!),
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
  };
}

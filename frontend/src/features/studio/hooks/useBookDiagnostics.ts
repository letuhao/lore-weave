import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';

// S-10 O3 — the studio Issues-tab data controller. Reads the book's ranked problems panel
// (GET /v1/composition/books/{id}/diagnostics) — error → warn → info, counts exact, rows capped.
// `enabled` lets the bottom panel fetch only when the Issues tab is actually open (it's a cheap read
// but still a round-trip). No JSX.
export function useBookDiagnostics(bookId: string | null | undefined, enabled: boolean) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ['composition', 'diagnostics', bookId],
    queryFn: () => compositionApi.getBookDiagnostics(bookId!, accessToken!),
    enabled: enabled && !!accessToken && !!bookId,
    staleTime: 30_000,
  });
  return {
    items: query.data?.items ?? [],
    counts: query.data?.counts ?? {},
    total: query.data?.total ?? 0,
    refsCapped: query.data?.refs_capped ?? false,
    warnings: query.data?.warnings ?? [],
    isLoading: query.isLoading && enabled,
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
    refetch: () => void query.refetch(),
  };
}

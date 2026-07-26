// M2 controller — the unified activity feed. Keyset-paginated (useInfiniteQuery over the BFF's
// opaque cursor) so a new notification arriving mid-scroll never dup/drops a row at a page boundary
// (MB3). Exposes the flattened items, the unread count, load-more, and a global mark-all-read that
// invalidates the feed. CLAUDE.md MVC: all logic here; the ActivityPage view only renders.
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { homeApi } from '../api';

export function useActivity() {
  const { accessToken } = useAuth();
  const qc = useQueryClient();

  const query = useInfiniteQuery({
    queryKey: ['activity'],
    queryFn: ({ pageParam }) => homeApi.getActivity(accessToken, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!accessToken,
    staleTime: 15_000,
  });

  const markAll = useMutation({
    mutationFn: () => homeApi.markAllRead(accessToken),
    onSuccess: () => {
      // Invalidate BOTH the feed and the home unread badge (a separate ['home'] query) so the
      // home Activity tile doesn't keep showing the old count after marking all read (M4).
      qc.invalidateQueries({ queryKey: ['activity'] });
      qc.invalidateQueries({ queryKey: ['home'] });
    },
  });

  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  // The unread count comes from the FIRST page (freshest); it's global-per-owner.
  const unread = query.data?.pages[0]?.unread_count ?? 0;

  return {
    items,
    unread,
    isLoading: query.isLoading,
    error: query.error as Error | null,
    hasMore: query.hasNextPage,
    isFetchingMore: query.isFetchingNextPage,
    loadMore: query.fetchNextPage,
    refetch: query.refetch,
    markAllRead: markAll.mutate,
    markingAll: markAll.isPending,
  };
}

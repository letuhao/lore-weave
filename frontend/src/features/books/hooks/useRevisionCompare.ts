// Chapter revision compare — controller. Owns the picked left/right revision
// ids + the view-mode, and drives the list (for the pickers) + the compare
// query. Defaults to the two newest revisions so the view shows the latest
// change immediately; the user can re-pick either side.
import { useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { booksApi } from '@/features/books/api';

export type CompareViewMode = 'side-by-side' | 'inline';

const PAGE = 100;

export function useRevisionCompare(
  token: string | null, bookId: string, chapterId: string,
  initial?: { leftId?: string; rightId?: string },
) {
  // #20_agent_mode.md D2 — an explicit initial pair (e.g. a unit's
  // pre_revision_id/post_revision_id from Agent Mode's diff panel) overrides
  // the "two newest revisions" default below. An explicit pick (setLeftId/
  // setRightId) always overrides both.
  const [leftId, setLeftId] = useState(initial?.leftId ?? '');
  const [rightId, setRightId] = useState(initial?.rightId ?? '');
  const [viewMode, setViewMode] = useState<CompareViewMode>('side-by-side');

  // Paginated so the picker can reach ANY revision, not just the newest 100
  // (D-COMPARE-PICKER-PAGINATION). Pages accumulate; `total` drives hasMore.
  const revisions = useInfiniteQuery({
    queryKey: ['revisions-paged', bookId, chapterId],
    queryFn: ({ pageParam }) => booksApi.listRevisions(token!, bookId, chapterId, { limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.items.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
    enabled: !!token && !!bookId && !!chapterId,
  });

  const items = revisions.data?.pages.flatMap((p) => p.items) ?? [];
  const total = revisions.data?.pages[0]?.total ?? items.length;
  // Default: right = newest (items[0]), left = the one before it (items[1]).
  // An explicit pick overrides. Derived (no useEffect) so a late list-load just
  // fills the defaults without a re-render loop.
  const effectiveRight = rightId || items[0]?.revision_id || '';
  const effectiveLeft = leftId || items[1]?.revision_id || '';

  const compare = useQuery({
    queryKey: ['revision-compare', bookId, chapterId, effectiveLeft, effectiveRight],
    queryFn: () => booksApi.compareRevisions(token!, bookId, chapterId, effectiveLeft, effectiveRight),
    enabled: !!token && !!effectiveLeft && !!effectiveRight,
  });

  return {
    revisions,
    compare,
    items,
    total,
    hasMore: revisions.hasNextPage,
    loadMore: () => revisions.fetchNextPage(),
    loadingMore: revisions.isFetchingNextPage,
    leftId: effectiveLeft,
    rightId: effectiveRight,
    setLeftId,
    setRightId,
    viewMode,
    setViewMode,
  };
}

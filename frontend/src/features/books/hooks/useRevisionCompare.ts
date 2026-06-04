// Chapter revision compare — controller. Owns the picked left/right revision
// ids + the view-mode, and drives the list (for the pickers) + the compare
// query. Defaults to the two newest revisions so the view shows the latest
// change immediately; the user can re-pick either side.
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { booksApi } from '@/features/books/api';

export type CompareViewMode = 'side-by-side' | 'inline';

export function useRevisionCompare(token: string | null, bookId: string, chapterId: string) {
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [viewMode, setViewMode] = useState<CompareViewMode>('side-by-side');

  const revisions = useQuery({
    queryKey: ['revisions', bookId, chapterId],
    queryFn: () => booksApi.listRevisions(token!, bookId, chapterId, { limit: 100 }),
    enabled: !!token && !!bookId && !!chapterId,
  });

  const items = revisions.data?.items ?? [];
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
    leftId: effectiveLeft,
    rightId: effectiveRight,
    setLeftId,
    setRightId,
    viewMode,
    setViewMode,
  };
}

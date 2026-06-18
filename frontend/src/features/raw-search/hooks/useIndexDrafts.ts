import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { rawSearchApi } from '../api';
import type { IndexDraftsResponse } from '../types';

// D-RAWSEARCH-CANON-WIRING — controller for the owner-only draft-indexing action.
// Draft semantic search (surface=all) is the book owner's private workspace, so
// the panel only exposes the toggle + the "index drafts" button to the owner.
// The BE enforces this independently (403 on non-owner index-drafts; a non-owner
// surface=all is silently downgraded to canon) — the FE gate is UX, not security.

export interface UseIndexDraftsResult {
  /** True only when the signed-in user owns this book. */
  isOwner: boolean;
  indexDrafts: () => void;
  isIndexing: boolean;
  result: IndexDraftsResponse | null;
  error: Error | null;
}

export function useIndexDrafts(bookId: string): UseIndexDraftsResult {
  const { accessToken, user } = useAuth();

  const bookQuery = useQuery({
    queryKey: ['book-owner', bookId] as const,
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken && !!bookId,
    staleTime: 5 * 60_000,
  });

  const isOwner =
    !!user?.user_id && bookQuery.data?.owner_user_id === user.user_id;

  const mutation = useMutation<IndexDraftsResponse, Error>({
    mutationFn: () => rawSearchApi.indexDrafts(bookId, accessToken!),
  });

  return {
    isOwner,
    indexDrafts: () => mutation.mutate(),
    isIndexing: mutation.isPending,
    result: mutation.data ?? null,
    error: (mutation.error as Error | null) ?? null,
  };
}

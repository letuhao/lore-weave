import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { fetchProposalInbox, type ProposalInbox } from '../lib/proposalsInbox';

// C11 (C11-proposals-inbox) — the Pending Proposals inbox query hook.
//
// Aggregates the 3 existing review queues (glossary AI-suggested drafts ·
// AI wiki suggestions · lore-enrichment proposals) for ONE book, read-only. All
// 3 sources are book-scoped, so the caller resolves the bookId from the
// route-scoped project (G6 — no project select-box) and passes it here.
//
// Per-source graceful degrade lives in fetchProposalInbox (each source is
// fetched independently); this hook just owns the query lifecycle. The
// query is enabled only once a bookId is known.

export interface UseProposalsInboxResult {
  inbox: ProposalInbox | null;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useProposalsInbox(
  bookId: string | null | undefined,
): UseProposalsInboxResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['knowledge-proposals-inbox', userId, bookId ?? null] as const,
    queryFn: () => fetchProposalInbox(bookId!, accessToken!),
    enabled: !!accessToken && !!bookId,
    staleTime: 30_000,
  });

  return {
    inbox: query.data ?? null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
    refetch: () => void query.refetch(),
  };
}

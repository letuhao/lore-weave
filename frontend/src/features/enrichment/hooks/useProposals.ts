import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { ReviewStatus } from '../types';

/** List the book's enrichment proposals (across general projects), optionally
 *  filtered by review_status. The list rows are full proposals (content +
 *  provenance), so the detail view reads from here — no separate fetch. Also
 *  derives the distinct project_ids present, which drives the client-side
 *  project picker. */
export function useProposals(
  bookId: string,
  opts: { reviewStatus?: ReviewStatus | 'all' } = {},
) {
  const { accessToken } = useAuth();
  const reviewStatus =
    opts.reviewStatus && opts.reviewStatus !== 'all' ? opts.reviewStatus : undefined;

  const query = useQuery({
    queryKey: ['enrichment-proposals', bookId, reviewStatus ?? 'all'],
    queryFn: () =>
      enrichmentApi.listProposals(bookId, { review_status: reviewStatus, limit: 100 }, accessToken!),
    enabled: !!accessToken && !!bookId,
  });

  const items = query.data?.items ?? [];
  const projectIds = useMemo(
    () => Array.from(new Set(items.map((p) => p.project_id))),
    [items],
  );

  return { ...query, items, total: query.data?.total ?? 0, projectIds };
}

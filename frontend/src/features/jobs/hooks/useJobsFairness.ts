import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { jobsApi } from '../api';

/** P5 — owner-scoped fair-scheduling depth ("N queued behind your cap"). Shares the
 *  ['jobs', ...] prefix so the SSE throttled-invalidate refreshes it as units dispatch
 *  and finalize. Also self-polls (30s) since the WFQ depth changes in Redis without a
 *  job-status SSE event (a chapter dispatched off the ready queue isn't a status change). */
export function useJobsFairness() {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['jobs', 'fairness'],
    queryFn: () => jobsApi.fairness(accessToken!),
    enabled: !!accessToken,
    refetchInterval: 30_000,
  });
}

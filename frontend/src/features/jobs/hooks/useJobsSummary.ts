import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { jobsApi } from '../api';

/** Owner-scoped status counts for the 4 summary cards. Shares the ['jobs', ...]
 *  prefix so the SSE throttled-invalidate refreshes the counts as jobs move
 *  between buckets. */
export function useJobsSummary() {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['jobs', 'summary'],
    queryFn: () => jobsApi.summary(accessToken!),
    enabled: !!accessToken,
  });
}

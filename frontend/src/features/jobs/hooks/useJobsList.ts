import { useInfiniteQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { jobsApi } from '../api';
import type { JobListParams } from '../types';

/** Owner-scoped job list (keyset cursor). The ['jobs', ...] key prefix lets the
 *  SSE throttled-invalidate + control mutations refresh it. Pass `parent` to load
 *  a parent's children; omit for the top-level view. */
export function useJobsList(filters: JobListParams = {}) {
  const { accessToken } = useAuth();
  return useInfiniteQuery({
    queryKey: ['jobs', 'list', filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      jobsApi.list({ ...filters, cursor: pageParam }, accessToken!),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!accessToken,
  });
}

import { useQuery, keepPreviousData } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { jobsApi } from '../api';
import type { JobListParams } from '../types';

/** History (terminal jobs) — offset pagination ordered by created_at DESC. Unlike
 *  the live Active list (keyset, in-place SSE updates), History is stable and
 *  paginated: it returns `total` for an "X–Y of N" pager. `page` is 0-based.
 *
 *  Shares the ['jobs', ...] key prefix so the SSE throttled-invalidate + control
 *  mutations refresh it (a job entering a terminal state appears here on the next
 *  flush). keepPreviousData avoids a flicker-to-empty while a page change loads. */
export function useJobsHistory(
  filters: Omit<JobListParams, 'bucket' | 'cursor' | 'offset' | 'parent'>,
  page: number,
  pageSize: number,
) {
  const { accessToken } = useAuth();
  return useQuery({
    queryKey: ['jobs', 'history', filters, page, pageSize],
    queryFn: () =>
      jobsApi.list(
        { ...filters, bucket: 'history', offset: page * pageSize, limit: pageSize },
        accessToken!,
      ),
    enabled: !!accessToken,
    placeholderData: keepPreviousData,
  });
}

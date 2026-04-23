import { useInfiniteQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type JobLog } from '../api';

// K19b.8 + C3 (D-K19b.8-03) — tail-follow + cursor pagination.
//
// K19b.8 shipped the single-page hook for a collapsed panel; C3
// extends to useInfiniteQuery so the panel can "Load more" for older
// pages AND auto-refetch every 5s while the job is still running.
// When the job reaches a terminal state (complete/failed/cancelled),
// the polling stops so we don't hammer Postgres for dead jobs.
//
// Tail-follow semantics: react-query's refetchInterval re-fetches
// ALL currently-loaded pages (keeping their original `pageParam`).
// The LAST page's cursor stays the same, but as the server adds new
// rows, that page's response grows. Once the response fills (50 rows)
// the BE returns `next_cursor != null` again, and `hasNextPage`
// flips back to true — the user sees "Load more" reappear. Matches
// cursor-pagination semantics without needing a separate tail query.

const DEFAULT_LIMIT = 50;
const TAIL_FOLLOW_INTERVAL_MS = 5_000;

export interface UseJobLogsResult {
  logs: JobLog[];
  hasNextPage: boolean;
  fetchNextPage: () => void;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  error: Error | null;
}

export interface UseJobLogsOptions {
  /**
   * When `'running'` / `'paused'` / `'pending'`, the hook polls every
   * TAIL_FOLLOW_INTERVAL_MS. On any terminal state, polling stops.
   * Omitted = poll defaults off (same as pre-C3 behaviour).
   */
  jobStatus?: string | null;
}

function shouldPoll(status: string | null | undefined): boolean {
  // Active states — the job may still be appending rows.
  return status === 'running' || status === 'paused' || status === 'pending';
}

export function useJobLogs(
  jobId: string | null,
  options: UseJobLogsOptions = {},
): UseJobLogsResult {
  const { accessToken } = useAuth();
  const { jobStatus } = options;

  const query = useInfiniteQuery({
    queryKey: ['knowledge-job-logs', jobId] as const,
    queryFn: ({ pageParam }) =>
      knowledgeApi.listJobLogs(
        jobId!,
        { sinceLogId: pageParam, limit: DEFAULT_LIMIT },
        accessToken!,
      ),
    initialPageParam: 0 as number,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!jobId && !!accessToken,
    staleTime: 10_000,
    refetchInterval: shouldPoll(jobStatus) ? TAIL_FOLLOW_INTERVAL_MS : false,
  });

  // Flatten all pages' logs into a single array for the component.
  const logs: JobLog[] =
    query.data?.pages.flatMap((p) => p.logs) ?? [];

  return {
    logs,
    hasNextPage: !!query.hasNextPage,
    fetchNextPage: () => {
      void query.fetchNextPage();
    },
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    error: (query.error as Error | null) ?? null,
  };
}

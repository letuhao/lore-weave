import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type JobLog } from '../api';

// K19b.8 — single-page job-logs hook for the JobLogsPanel inside
// JobDetailPanel. MVP: fetch the first page (up to `limit`, default
// 50) keyed by jobId. `staleTime: 10_000` dedupes rapid panel
// open/close cycles without actively polling. Load-more + tail-follow
// are deferred to a follow-up cycle.
//
// Disabled when no jobId or no accessToken. Returns `logs` always as
// an array (never null) so consumers can `.map` without a guard.

const DEFAULT_LIMIT = 50;

export interface UseJobLogsResult {
  logs: JobLog[];
  nextCursor: number | null;
  isLoading: boolean;
  error: Error | null;
}

export function useJobLogs(jobId: string | null): UseJobLogsResult {
  const { accessToken } = useAuth();

  const query = useQuery({
    queryKey: ['knowledge-job-logs', jobId, DEFAULT_LIMIT] as const,
    queryFn: () =>
      knowledgeApi.listJobLogs(
        jobId!,
        { limit: DEFAULT_LIMIT },
        accessToken!,
      ),
    enabled: !!jobId && !!accessToken,
    staleTime: 10_000,
  });

  return {
    logs: query.data?.logs ?? [],
    nextCursor: query.data?.next_cursor ?? null,
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
  };
}

import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type ExtractionJobWire } from '../api';

// K19b.1 — user-scoped cross-project jobs hook.
//
// Two independent queries so the cheap/active 2s poll doesn't drag
// the heavier history query along with it. Active jobs churn on every
// progress tick; history only churns when a job transitions into a
// terminal state, so 10s is fine.
//
// Both queries gate on `accessToken` to avoid firing before auth is
// ready. The React Query queryKey is scoped per user_id (review-impl
// L3) so cache entries from a prior user don't leak across a logout →
// login cycle on a shared QueryClient.
//
// Stale-on-error semantics (review-impl L2): after an initial success
// plus a later fetch failure, `active`/`history` still carry the last
// good snapshot (React Query keeps cached data across errors). The
// group-specific `activeError` / `historyError` fields let consumers
// render a banner or retry affordance without losing the old rows.

const ACTIVE_POLL_MS = 2_000;
const HISTORY_POLL_MS = 10_000;
const HISTORY_LIMIT = 50;

export interface UseExtractionJobsResult {
  active: ExtractionJobWire[];
  history: ExtractionJobWire[];
  isLoading: boolean;
  /** First error encountered, active takes precedence. `null` when clean. */
  error: Error | null;
  /** Group-specific errors so consumers can warn per-section. */
  activeError: Error | null;
  historyError: Error | null;
}

export function useExtractionJobs(): UseExtractionJobsResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const activeQuery = useQuery({
    queryKey: ['knowledge-jobs', userId, 'active'] as const,
    queryFn: () =>
      knowledgeApi.listAllJobs({ statusGroup: 'active' }, accessToken!),
    enabled: !!accessToken,
    refetchInterval: ACTIVE_POLL_MS,
  });

  const historyQuery = useQuery({
    queryKey: ['knowledge-jobs', userId, 'history', HISTORY_LIMIT] as const,
    queryFn: () =>
      knowledgeApi.listAllJobs(
        { statusGroup: 'history', limit: HISTORY_LIMIT },
        accessToken!,
      ),
    enabled: !!accessToken,
    refetchInterval: HISTORY_POLL_MS,
  });

  const activeError = (activeQuery.error as Error | null) ?? null;
  const historyError = (historyQuery.error as Error | null) ?? null;

  return {
    active: activeQuery.data ?? [],
    history: historyQuery.data ?? [],
    isLoading: activeQuery.isLoading || historyQuery.isLoading,
    error: activeError ?? historyError,
    activeError,
    historyError,
  };
}

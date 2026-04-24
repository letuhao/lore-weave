import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type ExtractionJobWire } from '../api';

// K19b.1 + C11 — user-scoped cross-project jobs hook.
//
// Two independent queries so the cheap/active 2s poll doesn't drag
// the heavier history query along with it. Active jobs churn on every
// progress tick; history only churns when a job transitions into a
// terminal state.
//
// C11 (D-K19b.1-01 + D-K19b.2-01): history uses ``useInfiniteQuery``
// with BE cursor pagination. Active stays on ``useQuery`` because it
// polls every 2s and is typically small (a handful of rows).
//
// Conditional polling (/review-impl MED#2): the history refetch
// interval is enabled ONLY when the user has 1 page loaded. Once they
// click Load more, polling stops — under infinite-query refetchInterval
// refetches ALL loaded pages, so a power user with 5 loaded pages
// would see 5× the BE load every tick. The "freeze on paginate"
// tradeoff is: single-page users still get newly-completed jobs
// within 10s; power users who explicitly expanded the view accept
// that they need to click Load more (or leave+return) to refresh.
//
// Both queries gate on ``accessToken`` to avoid firing before auth is
// ready. The React Query queryKey is scoped per user_id (review-impl
// L3) so cache entries from a prior user don't leak across a logout →
// login cycle on a shared QueryClient.
//
// Stale-on-error semantics (review-impl L2): after an initial success
// plus a later fetch failure, ``active``/``history`` still carry the
// last good snapshot (React Query keeps cached data across errors).
// The group-specific ``activeError`` / ``historyError`` fields let
// consumers render a banner or retry affordance without losing the
// old rows.

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
  /** C11: true when history has more pages the BE can return. */
  hasMoreHistory: boolean;
  /** C11: trigger a fetch of the next history page. No-op when
   *  ``hasMoreHistory`` is false or a fetch is already in flight. */
  fetchMoreHistory: () => void;
  /** C11: true while the next history page is loading. */
  isFetchingMoreHistory: boolean;
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

  const historyInfinite = useInfiniteQuery({
    queryKey: ['knowledge-jobs', userId, 'history', HISTORY_LIMIT] as const,
    queryFn: ({ pageParam }) =>
      knowledgeApi.listAllJobs(
        {
          statusGroup: 'history',
          limit: HISTORY_LIMIT,
          cursor: pageParam || undefined,
        },
        accessToken!,
      ),
    initialPageParam: '',
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!accessToken,
    // /review-impl MED#2: single-page polling. Returns HISTORY_POLL_MS
    // while the user has at most 1 page loaded (the typical case),
    // and false once they click Load more. Prevents the N-page
    // refetch storm while preserving the 10s freshness for users who
    // haven't opted into pagination.
    refetchInterval: (query) => {
      const pageCount = query.state.data?.pages.length ?? 0;
      return pageCount <= 1 ? HISTORY_POLL_MS : false;
    },
  });

  const activeError = (activeQuery.error as Error | null) ?? null;
  const historyError = (historyInfinite.error as Error | null) ?? null;

  const active = activeQuery.data?.items ?? [];
  // Flatten loaded pages in order — react-query preserves fetch
  // order in ``data.pages`` so the concat matches the BE's ORDER BY.
  const history =
    historyInfinite.data?.pages.flatMap((p) => p.items) ?? [];

  return {
    active,
    history,
    isLoading: activeQuery.isLoading || historyInfinite.isLoading,
    error: activeError ?? historyError,
    activeError,
    historyError,
    hasMoreHistory: historyInfinite.hasNextPage,
    fetchMoreHistory: () => {
      if (historyInfinite.hasNextPage && !historyInfinite.isFetchingNextPage) {
        void historyInfinite.fetchNextPage();
      }
    },
    isFetchingMoreHistory: historyInfinite.isFetchingNextPage,
  };
}

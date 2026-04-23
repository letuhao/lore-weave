import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type TimelineListParams,
  type TimelineResponse,
} from '../api';

// K19e.2 — browse hook for the Timeline tab. queryKey is userId-prefixed
// per the K19d β M1 precedent: without it, a logout→login swap on a
// shared QueryClient would flash the previous user's cached events for
// the 30s staleTime window. 30s matches the Entities tab — fresh enough
// for active curation, cache-hit-friendly for tab re-visits.

export interface UseTimelineResult {
  events: TimelineResponse['events'];
  total: number;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
}

export function useTimeline(params: TimelineListParams): UseTimelineResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: [
      'knowledge-timeline',
      userId,
      params.project_id ?? null,
      params.after_order ?? null,
      params.before_order ?? null,
      params.limit ?? 50,
      params.offset ?? 0,
    ] as const,
    queryFn: () => knowledgeApi.listTimeline(params, accessToken!),
    enabled: !!accessToken,
    staleTime: 30_000,
  });

  return {
    events: query.data?.events ?? [],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
  };
}

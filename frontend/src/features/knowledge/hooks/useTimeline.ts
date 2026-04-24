import { useEffect } from 'react';
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

export interface UseTimelineOptions {
  /** C7 (D-K19e-β-02) — stale-offset self-heal. Fires when the server
   *  returns empty events for a non-zero offset but total>0 (another
   *  client's delete shrank the dataset past the current page). Parent
   *  is expected to reset its offset state to 0 so the next query
   *  lands on a valid page. The "Back to first" button in TimelineTab
   *  stays as a defense-in-depth fallback. */
  onStaleOffset?: () => void;
}

export interface UseTimelineResult {
  events: TimelineResponse['events'];
  total: number;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
}

export function useTimeline(
  params: TimelineListParams,
  options?: UseTimelineOptions,
): UseTimelineResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: [
      'knowledge-timeline',
      userId,
      params.project_id ?? null,
      params.after_order ?? null,
      params.before_order ?? null,
      // C10 (D-K19e-α-01 + D-K19e-α-03): new filters become part of
      // the cache key so changing them triggers a refetch.
      params.after_chronological ?? null,
      params.before_chronological ?? null,
      params.entity_id ?? null,
      params.limit ?? 50,
      params.offset ?? 0,
    ] as const,
    queryFn: () => knowledgeApi.listTimeline(params, accessToken!),
    enabled: !!accessToken,
    staleTime: 30_000,
  });

  const events = query.data?.events ?? [];
  const total = query.data?.total ?? 0;
  const offset = params.offset ?? 0;
  const isLoading = query.isLoading;
  const isFetching = query.isFetching;
  const error = (query.error as Error | null) ?? null;

  const onStaleOffset = options?.onStaleOffset;
  useEffect(() => {
    if (
      onStaleOffset &&
      total > 0 &&
      offset > 0 &&
      events.length === 0 &&
      !isLoading &&
      !isFetching &&
      !error
    ) {
      onStaleOffset();
    }
  }, [onStaleOffset, total, offset, events.length, isLoading, isFetching, error]);

  return { events, total, isLoading, isFetching, error };
}

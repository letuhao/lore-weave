import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type GapReportResponse } from '../api';

// C10 (C10-gap-report) — entity Gap Report query hook.
//
// Fetches knowledge-service's find_gap_candidates() for ONE project
// (route-scoped, G6): high-mention DISCOVERED entities with no glossary
// entry. `minMentions` + `limit` are part of the queryKey so changing
// the threshold control refetches. userId-prefixed key, matching the
// useEntities precedent (no cross-user cache bleed on a shared client).
//
// NOTE — this is ENTITY gaps. It is NOT the lore-enrichment
// attribute-dimension gaps (features/enrichment/hooks/useGaps). Two
// distinct concepts; kept separate by lock.

export interface UseGapsResult {
  gaps: GapReportResponse['gaps'];
  total: number;
  /** The threshold the BE actually applied (echoed back). */
  appliedMinMentions: number;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useGaps(args: {
  projectId: string | undefined;
  minMentions: number;
  limit: number;
}): UseGapsResult {
  const { projectId, minMentions, limit } = args;
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: [
      'knowledge-gaps',
      userId,
      projectId ?? null,
      minMentions,
      limit,
    ] as const,
    queryFn: () =>
      knowledgeApi.getProjectGaps(
        projectId!,
        { min_mentions: minMentions, limit },
        accessToken!,
      ),
    enabled: !!accessToken && !!projectId,
    staleTime: 30_000,
  });

  return {
    gaps: query.data?.gaps ?? [],
    total: query.data?.total ?? 0,
    appliedMinMentions: query.data?.min_mentions ?? minMentions,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
    refetch: () => void query.refetch(),
  };
}

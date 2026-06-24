import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type TimelineEvent } from '@/features/knowledge/api';

// D-WORLD-TIMELINE-ROLLUP — world timeline rollup DATA controller (FE MVC).
// Sources from the BE union `GET /v1/knowledge/worlds/{id}/timeline` — the
// timeline mirror of useWorldSubgraph. Read-only; events carry `project_id`,
// so the view can legend the per-book islands.
const ROLLUP_LIMIT = 100;

export function useWorldTimeline(worldId: string | undefined) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['world-timeline', userId, worldId ?? null] as const,
    queryFn: () =>
      knowledgeApi.getWorldTimeline(worldId!, { sort_by: 'narrative', limit: ROLLUP_LIMIT }, accessToken!),
    enabled: !!accessToken && !!worldId,
    staleTime: 30_000,
  });

  const events: TimelineEvent[] = useMemo(() => query.data?.events ?? [], [query.data]);

  // Distinct source books contributing to the union (legend).
  const sourceCount = useMemo(() => {
    const ids = new Set<string>();
    for (const e of events) ids.add(e.project_id ?? 'unknown');
    return ids.size;
  }, [events]);

  return {
    events,
    sourceCount,
    truncated: query.data?.truncated ?? false,
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
  };
}

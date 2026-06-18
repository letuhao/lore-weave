import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type SubgraphNode, type SubgraphEdge } from '@/features/knowledge/api';

// W5 (G4) — world rollup graph DATA controller. Owns the fetch so
// WorldRollupGraph stays a pure view (FE MVC). Sources from W2's
// `GET /v1/knowledge/worlds/{id}/subgraph` — the app-side UNION of each
// member book's canon subgraph + the world-level project.
//
// Unlike useProjectSubgraph there is NO expand-hop: the world rollup is a
// flat union of per-book islands (disconnected components by design — C18
// edges are intra-partition only), and the endpoint has no `center`
// parameter. The server caps the union (`node_cap_hit`); the FE just renders.

const ROLLUP_LIMIT = 200;

export interface WorldSubgraphSource {
  /** The member project this island came from (`source_project_id`). */
  projectId: string;
  nodeCount: number;
}

export function useWorldSubgraph(worldId: string | undefined) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['world-subgraph', userId, worldId ?? null] as const,
    queryFn: () => knowledgeApi.getWorldSubgraph(worldId!, { limit: ROLLUP_LIMIT }, accessToken!),
    enabled: !!accessToken && !!worldId,
    staleTime: 30_000,
  });

  const nodes: SubgraphNode[] = useMemo(() => query.data?.nodes ?? [], [query.data]);
  const edges: SubgraphEdge[] = useMemo(() => query.data?.edges ?? [], [query.data]);

  // Per-source island breakdown (legend): how many nodes each member project
  // contributed. Nodes without a source_project_id (defensive — the rollup
  // always tags them) collapse into a single 'unknown' bucket.
  const sources: WorldSubgraphSource[] = useMemo(() => {
    const counts = new Map<string, number>();
    for (const n of nodes) {
      const pid = n.source_project_id ?? 'unknown';
      counts.set(pid, (counts.get(pid) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([projectId, nodeCount]) => ({ projectId, nodeCount }))
      .sort((a, b) => b.nodeCount - a.nodeCount);
  }, [nodes]);

  return {
    nodes,
    edges,
    sources,
    truncated: query.data?.node_cap_hit ?? false,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
    refetch: () => void query.refetch(),
  };
}

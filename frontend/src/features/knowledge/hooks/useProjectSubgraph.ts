import { useCallback, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type SubgraphResponse,
  type SubgraphNode,
  type SubgraphEdge,
} from '../api';

// C19 (G5) — project graph-canvas DATA controller. Owns ALL fetch /
// cache / merge logic so the ProjectGraphView component stays a pure
// view (FE MVC rule: no fetch/merge inside the component).
//
// The graph is read from C18's `GET /projects/{id}/subgraph`. The base
// fetch is project-wide (top-N, node-capped). Expand-hop accretes: a
// click on a node's ⊞ re-queries C18 with `center=<id>` (a bounded
// ego-neighbourhood) and MERGES the result into the accreted set —
// NOT a full reload. The node cap is honoured FE-side too: the merged
// set never grows past `nodeCap`, so a runaway expand can't OOM the SVG.

/** FE hard cap on the accreted (base + all expansions) node set. The BE
 *  caps each individual query; this bounds the union so repeated
 *  expand-hops can't render an unbounded graph (DOM/SVG perf collapse). */
export const SUBGRAPH_VIEW_NODE_CAP = 250;
const BASE_LIMIT = 150;
const EXPAND_LIMIT = 60;
const EXPAND_HOPS = 1;

export interface MergedSubgraph {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
  /** True when either the base query hit its cap OR the FE union cap
   *  trimmed accreted nodes — drives the "expand to load more" banner. */
  truncated: boolean;
}

// Pure (exported for tests): merge an incoming subgraph payload into the
// already-accreted set. Nodes dedupe by id (incoming wins — fresher
// projection); edges dedupe by id. The union is capped at `cap`
// (existing nodes kept first so the user's current view is stable);
// edges to dropped nodes are pruned. `truncated` reflects either the
// payload's own cap hit OR the union cap trimming.
export function mergeSubgraph(
  prev: MergedSubgraph,
  incoming: SubgraphResponse,
  cap: number = SUBGRAPH_VIEW_NODE_CAP,
): MergedSubgraph {
  const nodes = new Map<string, SubgraphNode>();
  for (const n of prev.nodes) nodes.set(n.id, n);
  for (const n of incoming.nodes) nodes.set(n.id, n); // incoming wins

  let nodeList = [...nodes.values()];
  const unionTrimmed = nodeList.length > cap;
  if (unionTrimmed) nodeList = nodeList.slice(0, cap); // existing-first keeps the view stable
  const kept = new Set(nodeList.map((n) => n.id));

  const edges = new Map<string, SubgraphEdge>();
  for (const e of prev.edges) if (kept.has(e.source) && kept.has(e.target)) edges.set(e.id, e);
  for (const e of incoming.edges) if (kept.has(e.source) && kept.has(e.target)) edges.set(e.id, e);

  return {
    nodes: nodeList,
    edges: [...edges.values()],
    truncated: prev.truncated || incoming.node_cap_hit || unionTrimmed,
  };
}

const EMPTY: MergedSubgraph = { nodes: [], edges: [], truncated: false };

/**
 * Resolve the project's base subgraph + accrete expand-hops.
 *
 * The base project-wide subgraph is a react-query (cached by
 * user+project). Expansions are imperative: `expand(id)` fetches the
 * ego-neighbourhood of `id` and folds it into local accreted state via
 * `mergeSubgraph`. The view = base ∪ accreted, capped. `expand` is
 * called from the node's click handler (NOT a useEffect reacting to
 * state — the FE event rule).
 */
export function useProjectSubgraph(projectId: string | undefined, enabled: boolean = true) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const baseQuery = useQuery({
    queryKey: ['knowledge-subgraph', userId, projectId ?? null] as const,
    queryFn: () =>
      knowledgeApi.getProjectSubgraph(
        projectId!,
        { limit: BASE_LIMIT },
        accessToken!,
      ),
    // S-09 W3 — idle when the panel is in view/as-of lens mode (the sibling
    // useProjectGraphSlice reads the filtered graph instead), so the two data
    // sources never double-fetch.
    enabled: enabled && !!accessToken && !!projectId,
    staleTime: 30_000,
  });

  // Accreted expansions, merged on top of the base.
  const [accreted, setAccreted] = useState<MergedSubgraph>(EMPTY);
  const [expandingId, setExpandingId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<string[]>([]);

  // Reset the accreted state when the base-query identity (user+project)
  // changes. The shell route (`/knowledge/projects/:projectId/:section`)
  // re-renders rather than remounts on a project switch, so without this
  // reset project A's expansions would bleed into project B's canvas
  // (foreign nodes rendered + B's cap consumed). Done via the
  // store-prev-key-in-a-ref render-time pattern — NOT a useEffect (which
  // would paint one stale frame first). Adversary C19 MAJOR fix.
  const baseKey = `${userId}::${projectId ?? ''}`;
  const keyRef = useRef(baseKey);
  if (keyRef.current !== baseKey) {
    keyRef.current = baseKey;
    setAccreted(EMPTY);
    setExpandedIds([]);
    setExpandingId(null);
  }

  const base: MergedSubgraph = useMemo(
    () =>
      baseQuery.data
        ? {
            nodes: baseQuery.data.nodes,
            edges: baseQuery.data.edges,
            truncated: baseQuery.data.node_cap_hit,
          }
        : EMPTY,
    [baseQuery.data],
  );

  // The rendered graph: base merged with every accreted expansion.
  const merged = useMemo(
    () =>
      mergeSubgraph(base, { nodes: accreted.nodes, edges: accreted.edges, node_cap_hit: accreted.truncated }),
    [base, accreted],
  );

  // Expand-hop: re-query C18 for the ego-neighbourhood of `id` and fold
  // it in — NO full reload. Fired from the node click handler. Idempotent:
  // a node already expanded (or an in-flight one) is a no-op, so re-clicking
  // the ⊞ never fires a redundant query (the glyph reads as "expanded"
  // thereafter; collapse is intentionally out of this read-only MVP's scope).
  const expand = useCallback(
    async (id: string) => {
      if (!accessToken || !projectId) return;
      if (expandedIds.includes(id) || expandingId === id) return;
      setExpandingId(id);
      try {
        const ego = await queryClient.fetchQuery({
          queryKey: ['knowledge-subgraph-ego', userId, projectId, id] as const,
          queryFn: () =>
            knowledgeApi.getProjectSubgraph(
              projectId,
              { center: id, hops: EXPAND_HOPS, limit: EXPAND_LIMIT },
              accessToken,
            ),
          staleTime: 30_000,
        });
        setAccreted((prev) => mergeSubgraph(prev, ego));
        setExpandedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
      } finally {
        setExpandingId(null);
      }
    },
    [accessToken, projectId, userId, queryClient, expandedIds, expandingId],
  );

  return {
    nodes: merged.nodes,
    edges: merged.edges,
    truncated: merged.truncated,
    expandedIds,
    expandingId,
    expand,
    isLoading: baseQuery.isLoading,
    isFetching: baseQuery.isFetching,
    error: (baseQuery.error as Error | null) ?? null,
    refetch: () => void baseQuery.refetch(),
  };
}

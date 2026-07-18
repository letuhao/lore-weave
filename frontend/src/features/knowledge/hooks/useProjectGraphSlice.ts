import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';
import type { GraphSlice } from '../types/ontology';

// S-09 W3 (F-12) — view-aware / temporal graph DATA controller.
//
// The sibling `useProjectSubgraph` reads the top-N `/subgraph` (params
// center/hops/limit) and accretes ego-expansions. THIS hook reads the
// view-aware `GET /projects/{id}/graph?view=&as_of_chapter=` reader
// (graph_views.py) — the whole project graph filtered by a saved lens
// (edge-type + node-kind allow-sets) AND an as-of-chapter temporal cut.
// There is no expand-hop here: the lens IS the scope, so the slice is
// rendered whole. The two hooks are swapped by ProjectGraphView based on
// whether a lens is active, and this one returns the SAME shape as
// useProjectSubgraph so the component stays a pure view (FE MVC).
//
// The reader returns GraphNode {id,kind,name,*_label} + GraphEdge
// {edge_type,source_id,target_id,valid_*,edge_type_label}. We normalize to
// the canvas's {id,name,kind} node + {id,source,target,predicate,confidence}
// edge — preferring the localized *_label when present (the reader localizes
// for the caller's reader-language, C7). Edges carry no id from the reader,
// so we synthesize a stable key from (source,edge_type,target,index).

export interface GraphSliceNodeView {
  id: string;
  name: string;
  kind: string;
  glossary_entity_id?: string | null;
}

export interface GraphSliceEdgeView {
  id: string;
  source: string;
  target: string;
  predicate: string;
  confidence: number;
}

export interface ProjectGraphSliceResult {
  nodes: GraphSliceNodeView[];
  edges: GraphSliceEdgeView[];
  /** Deprecated-edge-type notices from the view lens (§10-A4). */
  warnings: string[];
  /** True when the reader hit its edge `limit` (the slice may be partial). */
  truncated: boolean;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  refetch: () => void;
  // Parity with useProjectSubgraph so the two are drop-in swappable. Lens mode
  // has no expand-hop (the lens is the whole scope), so these are inert.
  expandedIds: string[];
  expandingId: string | null;
  expand: (id: string) => void;
}

// Pure (exported for tests): normalize a reader slice onto the canvas view
// shapes, preferring localized labels and synthesizing stable edge ids.
export function normalizeSlice(slice: GraphSlice): {
  nodes: GraphSliceNodeView[];
  edges: GraphSliceEdgeView[];
} {
  const nodes = slice.nodes.map((n) => ({
    id: n.id,
    name: n.name_label ?? n.name,
    kind: n.kind_label ?? n.kind,
    glossary_entity_id: n.glossary_entity_id ?? null,
  }));
  const edges = slice.edges.map((e, i) => ({
    id: `${e.source_id}|${e.edge_type}|${e.target_id}|${i}`,
    source: e.source_id,
    target: e.target_id,
    predicate: e.edge_type_label ?? e.edge_type,
    confidence: 1, // the reader returns only active (valid_until IS NULL) edges
  }));
  return { nodes, edges };
}

const READ_LIMIT = 1000;

/**
 * Read the project graph through a saved view lens and/or an as-of-chapter
 * cut. `viewCode`/`asOfChapter` null ⇒ the caller isn't in lens mode; pass
 * `enabled=false` so the query stays idle (ProjectGraphView uses the sibling
 * subgraph hook then). Keyed by (user, project, view, as-of) so switching the
 * lens refetches and switching back hits the cache.
 */
export function useProjectGraphSlice(
  projectId: string | undefined,
  viewCode: string | null,
  asOfChapter: number | null,
  enabled: boolean,
): ProjectGraphSliceResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['knowledge-graph-slice', userId, projectId ?? null, viewCode, asOfChapter] as const,
    queryFn: () =>
      ontologyApi.readGraph(
        projectId!,
        {
          ...(viewCode ? { view: viewCode } : {}),
          ...(asOfChapter != null ? { as_of_chapter: asOfChapter } : {}),
          limit: READ_LIMIT,
        },
        accessToken!,
      ),
    enabled: enabled && !!accessToken && !!projectId,
    staleTime: 30_000,
  });

  const view = useMemo(() => {
    if (!query.data) return { nodes: [], edges: [] };
    return normalizeSlice(query.data);
  }, [query.data]);

  return {
    nodes: view.nodes,
    edges: view.edges,
    warnings: query.data?.warnings ?? [],
    truncated: (query.data?.edges.length ?? 0) >= READ_LIMIT,
    isLoading: query.isLoading && enabled,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
    refetch: () => void query.refetch(),
    expandedIds: [],
    expandingId: null,
    expand: () => {},
  };
}

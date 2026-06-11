// LOOM Composition (T2.2) — Relationship Map controller. An ego-network over the
// knowledge graph: a focus entity + its 1-hop RELATES_TO relations, expandable by
// accretion (click a neighbor to re-focus, expand a node to pull its 1-hop). No
// whole-graph endpoint exists, so the graph is assembled client-side from
// `GET /entities/{id}` details. Pure buildGraph/radialLayout are exported for tests.
import { useMemo, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '../../knowledge/api';
import type { EntityDetail } from '../../knowledge/api';
import { useKnowledgeProjectId } from './useCast';
import type { Pos } from '../components/GraphCanvas';

export type GraphNode = { id: string; name: string; kind: string };
export type GraphEdge = {
  id: string; from: string; to: string; predicate: string; pending: boolean; confidence: number;
};

export const RELMAP_NODE_CAP = 60;

// Pure (exported for tests): assemble the ego-network from the accreted entity
// details. Nodes = every focused entity (full data) PLUS each relation's two
// endpoints (name/kind from the relation projection — neighbours we may not have
// detail for yet). Edges = all relations, deduped by id. Focused-entity nodes win
// over relation-derived stubs (richer name). Capped at RELMAP_NODE_CAP (focused
// entities are kept first); edges to dropped nodes are pruned. `truncated` flags
// the overflow so the UI never silently hides nodes.
export function buildGraph(
  details: Record<string, EntityDetail>,
): { nodes: GraphNode[]; edges: GraphEdge[]; truncated: boolean } {
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();
  const focusedIds = Object.keys(details);

  // 1. focused entities first (authoritative name/kind) — preserves cap priority.
  for (const id of focusedIds) {
    const e = details[id].entity;
    nodes.set(id, { id, name: e.name, kind: e.kind });
  }
  // 2. relations → edges + neighbour stubs (don't overwrite a focused node).
  for (const id of focusedIds) {
    for (const r of details[id].relations) {
      if (!nodes.has(r.subject_id)) nodes.set(r.subject_id, { id: r.subject_id, name: r.subject_name ?? r.subject_id, kind: r.subject_kind ?? 'concept' });
      if (!nodes.has(r.object_id)) nodes.set(r.object_id, { id: r.object_id, name: r.object_name ?? r.object_id, kind: r.object_kind ?? 'concept' });
      if (!edges.has(r.id)) edges.set(r.id, {
        id: r.id, from: r.subject_id, to: r.object_id,
        predicate: r.predicate, pending: r.pending_validation, confidence: r.confidence,
      });
    }
  }

  let nodeList = [...nodes.values()];
  const truncated = nodeList.length > RELMAP_NODE_CAP;
  if (truncated) nodeList = nodeList.slice(0, RELMAP_NODE_CAP); // focused-first order keeps the focus chain
  const kept = new Set(nodeList.map((n) => n.id));
  const edgeList = [...edges.values()].filter((e) => kept.has(e.from) && kept.has(e.to));
  return { nodes: nodeList, edges: edgeList, truncated };
}

// Pure (exported for tests): radial layout — focus at center, the rest on
// concentric rings (deterministic by sorted id), then normalised so the
// top-left node sits at (PAD, PAD) (no negative coords for the SVG extent).
export function radialLayout(
  nodeIds: string[],
  focusId: string | null,
  opts: { cx?: number; cy?: number; r0?: number; ringGap?: number; pad?: number } = {},
): Record<string, Pos> {
  const { cx = 320, cy = 280, r0 = 150, ringGap = 120, pad = 24 } = opts;
  const out: Record<string, Pos> = {};
  if (focusId && nodeIds.includes(focusId)) out[focusId] = { x: cx, y: cy };
  const others = nodeIds.filter((id) => id !== focusId).sort();
  let i = 0;
  let ring = 0;
  while (i < others.length) {
    const radius = r0 + ring * ringGap;
    const cap = Math.max(6, Math.floor((2 * Math.PI * radius) / 110)); // ~110px arc spacing
    const count = Math.min(cap, others.length - i);
    for (let j = 0; j < count; j++) {
      const angle = (2 * Math.PI * j) / count - Math.PI / 2;
      out[others[i + j]] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
    }
    i += count;
    ring++;
  }
  // normalise so the minimum corner is at (pad, pad)
  const xs = Object.values(out).map((p) => p.x);
  const ys = Object.values(out).map((p) => p.y);
  if (xs.length) {
    const dx = pad - Math.min(...xs);
    const dy = pad - Math.min(...ys);
    for (const id of Object.keys(out)) out[id] = { x: out[id].x + dx, y: out[id].y + dy };
  }
  return out;
}

/**
 * Ego-network state: resolve the book's knowledge project, list its entities (for
 * the focus picker), hold the focus + the expanded set, and fetch `GET /entities/
 * {id}` for each (focus + expanded) so buildGraph can assemble the view.
 */
export function useRelationshipMap(bookId: string | undefined, token: string | null) {
  const projectQ = useKnowledgeProjectId(bookId, token);
  const projectId = projectQ.data;

  const entitiesQ = useQuery({
    queryKey: ['composition', 'relmap', 'entities', projectId],
    queryFn: () => knowledgeApi.listEntities({ project_id: projectId!, limit: 200 }, token!),
    enabled: !!projectId && !!token,
    select: (d) => d.entities,
    staleTime: 5 * 60 * 1000,
  });
  const entities = entitiesQ.data ?? [];

  const [focusId, setFocusId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  // Derive the active focus (default to the first entity) without a useEffect.
  const effectiveFocus = focusId ?? entities[0]?.id ?? null;

  const detailIds = useMemo(
    () => [...new Set([effectiveFocus, ...expanded].filter((x): x is string => !!x))],
    [effectiveFocus, expanded],
  );
  const detailQueries = useQueries({
    queries: detailIds.map((id) => ({
      queryKey: ['composition', 'relmap', 'detail', id],
      queryFn: () => knowledgeApi.getEntityDetail(id, token!),
      enabled: !!token,
      staleTime: 60 * 1000,
    })),
  });

  const details: Record<string, EntityDetail> = {};
  detailQueries.forEach((q, i) => { if (q.data) details[detailIds[i]] = q.data; });

  const setFocus = (id: string) => { setFocusId(id); setExpanded([]); }; // refocus resets accretion
  const toggleExpand = (id: string) =>
    setExpanded((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  return {
    projectId, projectLoading: projectQ.isLoading,
    entities, entitiesLoading: entitiesQ.isLoading,
    focusId: effectiveFocus, setFocus,
    expanded, toggleExpand,
    details, detailsLoading: detailQueries.some((q) => q.isLoading),
  };
}

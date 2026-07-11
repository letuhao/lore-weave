// Plan Hub v2 (24 H3.3 / PH16) — the drawer's PER-NODE detail controller. On selection the drawer
// needs the WHOLE node, not the canvas's L1-ref summary (PH10): a chapter/scene fetches its full
// outline node (GET /outline/nodes/{id} — the composition_get_outline_node REST mirror), and an
// arc/saga reads its row from the arc SHELL usePlanHub already loaded (same query key ⇒ no extra
// request). Cast entity ids resolve to names via the shared glossary roster. All render-only: the
// drawer edits nothing here — writes are H5 / PH20.
//
// DOCK-2 reuse notes (no forks):
//   • the per-node fetch is `compositionApi.getNode` — the ONE owner of that route string. A second
//     `plan-hub/api.getOutlineNode` would re-encode the same URL and drift on any route change.
//   • the arc row is the SAME `getArcs` shell cache usePlanHub populates (`['plan-hub','arcs',id]`).
//   • cast names come from `useGlossaryRoster` (the scene-inspector's roster hook), shared cache.
import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import { useGlossaryRoster } from '@/features/composition/hooks/useGlossaryRoster';
import type { OutlineNode } from '@/features/composition/types';

import { getArcs } from '../api';
import type { ArcListNode } from '../types';

/** The drawer's node families: outline (chapter/scene) vs structure (arc/saga). `unknown` when the
 *  panel hasn't resolved a kind yet (nothing selected, or the node's content window not loaded). */
export type PlanNodeKind = 'chapter' | 'scene' | 'arc' | 'saga' | 'unknown';

export function normalizeKind(kind: string | null | undefined): PlanNodeKind {
  if (kind === 'chapter' || kind === 'scene' || kind === 'arc' || kind === 'saga') return kind;
  return 'unknown';
}

export interface PlanNodeView {
  kind: PlanNodeKind;
  /** The full outline node (chapter/scene) — null until it loads / for arc kinds. */
  outlineNode: OutlineNode | null;
  /** The arc shell row (arc/saga) — null for outline kinds / when the id isn't in the shell. */
  arcNode: ArcListNode | null;
  loading: boolean;
  error: string | null;
  /** Resolve a glossary entity id → display name. null id → null; an unresolved id returns the raw
   *  id (never a silent blank — PH26). The full missing-vs-truncated split is H4.4's cast-chip work. */
  nameFor: (id: string | null | undefined) => string | null;
}

export function usePlanNode(
  bookId: string,
  nodeId: string | null,
  kind: string | null,
): PlanNodeView {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const k = normalizeKind(kind);
  const isOutline = k === 'chapter' || k === 'scene';
  const isArc = k === 'arc' || k === 'saga';

  // Outline detail — the drawer's per-node full fetch (chapter/scene only). Keyed on nodeId alone
  // (getNode is a by-id read; ids are globally unique). Disabled for arc kinds / no selection.
  const outlineQuery = useQuery({
    queryKey: ['plan-hub', 'node', nodeId],
    queryFn: () => compositionApi.getNode(nodeId!, token!),
    enabled: !!token && !!nodeId && isOutline,
  });

  // Arc shell — the SAME query usePlanHub loads; TanStack dedupes to one fetch and serves cache.
  const arcsQuery = useQuery({
    queryKey: ['plan-hub', 'arcs', bookId],
    queryFn: () => getArcs(bookId, token!),
    enabled: !!token && !!bookId && isArc,
  });

  // Cast-name map (glossary roster — DOCK-2). Cached per book, shared with the scene-inspector.
  const roster = useGlossaryRoster(bookId || undefined, token);
  const nameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of roster.data ?? []) m.set(o.id, o.label);
    return m;
  }, [roster.data]);
  const nameFor = useCallback(
    (id: string | null | undefined): string | null => (id ? nameMap.get(id) ?? id : null),
    [nameMap],
  );

  const arcNode = useMemo(
    () => (isArc ? arcsQuery.data?.arcs.find((a) => a.id === nodeId) ?? null : null),
    [isArc, arcsQuery.data, nodeId],
  );

  // Loading = actively fetching with nothing to show yet (version-agnostic across react-query
  // majors; a disabled query never fetches, so it never reads as loading — absent ≠ loading).
  const outlineLoading = isOutline && !outlineQuery.data && outlineQuery.isFetching;
  const arcLoading = isArc && !arcsQuery.data && arcsQuery.isFetching;
  const loading = outlineLoading || arcLoading;

  const errOf = (e: unknown): string | null => (e instanceof Error ? e.message : null);
  const error = isOutline ? errOf(outlineQuery.error) : isArc ? errOf(arcsQuery.error) : null;

  return {
    kind: k,
    outlineNode: isOutline ? outlineQuery.data ?? null : null,
    arcNode,
    loading,
    error,
    nameFor,
  };
}

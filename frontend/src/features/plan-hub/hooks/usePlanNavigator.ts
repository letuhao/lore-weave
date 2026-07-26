// Plan Hub v2 (24 §Phase H6 / PH25) — the CONTROLLER for the Plan navigator rail. Owns the arc-shell
// fetch, the collapse state, and the tree flatten; the rail component renders the result only.
//
// PH25: the rail is "the same fetch as the Hub" (the list rendering of the SAME arc shell the canvas
// draws). So the query reuses usePlanHub's shell key + fetcher → react-query DEDUPES: rail + canvas
// share ONE getArcs call when both are mounted. This never re-implements "where does a node go"
// (PH14): the canvas renders POSITIONS, the rail renders ORDER, both from this one shell read.
import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { getArcs } from '../api';
import type { ArcListNode } from '../types';

/** One flattened rail row: the shell node + its TREE-derived depth. `depth` is recomputed from the
 *  parent_id tree here (the shell's own `depth` field is NOT trusted — laneLayout parity, where a
 *  LaneBand's depth is likewise recomputed), so a stale/miswritten depth can't mis-indent the rail. */
export interface PlanNavRow {
  node: ArcListNode;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
}

// Compare two lexranks (then id) — the same (rank, id) sibling order laneLayout.byRank lays lanes
// out by, so the rail's row order mirrors the canvas's lane order exactly.
function byRank(a: ArcListNode, b: ArcListNode): number {
  if (a.rank < b.rank) return -1;
  if (a.rank > b.rank) return 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

/**
 * Pure (exported for tests): flatten the arc shell into a depth-annotated pre-order list, skipping
 * the children of collapsed nodes. Depth is derived from the parent_id tree. A parent_id pointing
 * outside the shell is treated as a root (never orphan-drop a node — mirrors buildForest's
 * defensive rooting); a duplicate/cyclic id never renders twice.
 */
export function flattenArcShell(shell: ArcListNode[], collapsed: Set<string>): PlanNavRow[] {
  const byId = new Set(shell.map((n) => n.id));
  const byParent = new Map<string | null, ArcListNode[]>();
  for (const n of shell) {
    const key = n.parent_id && byId.has(n.parent_id) ? n.parent_id : null;
    const arr = byParent.get(key) ?? [];
    arr.push(n);
    byParent.set(key, arr);
  }
  for (const arr of byParent.values()) arr.sort(byRank);
  const out: PlanNavRow[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const n of byParent.get(parent) ?? []) {
      if (seen.has(n.id)) continue;
      seen.add(n.id);
      const hasChildren = byParent.has(n.id);
      out.push({ node: n, depth, hasChildren, expanded: !collapsed.has(n.id) });
      if (hasChildren && !collapsed.has(n.id)) walk(n.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

export interface PlanNavigatorState {
  rows: PlanNavRow[];
  loading: boolean;
  error: string | null;
  /** Collapse/expand a node's subtree (the shell is one bounded call — no lazy load on expand). */
  toggle: (id: string) => void;
}

export function usePlanNavigator(bookId: string): PlanNavigatorState {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const enabled = !!token && !!bookId;

  const arcsQuery = useQuery({
    queryKey: ['plan-hub', 'arcs', bookId], // shared with usePlanHub → one getArcs call (PH25)
    queryFn: () => getArcs(bookId, token!),
    enabled,
  });

  // Opened-by-default model: an id in `collapsed` hides its subtree (default none ⇒ whole shell
  // visible). Tracking the COLLAPSED ids (not the open ones) means a fresh shell shows expanded.
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());

  const rows = useMemo(
    () => flattenArcShell(arcsQuery.data?.arcs ?? [], collapsed),
    [arcsQuery.data, collapsed],
  );

  const toggle = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  return {
    rows,
    loading: enabled && arcsQuery.isLoading,
    error: arcsQuery.error instanceof Error ? arcsQuery.error.message : null,
    toggle,
  };
}

// Pure tree operations for the manuscript navigator — no React, fully unit-testable.
import { ROOT_KEY, type ManuscriptNode, type ManuscriptRow, type TreeState } from './types';

/** Whether a parent key has an unfetched next page (cursor is a non-empty string). */
export function hasMore(state: TreeState, parentKey: string): boolean {
  return typeof state.childCursor[parentKey] === 'string';
}

/**
 * Flatten the loaded + expanded tree into ordered render rows (depth-first). Each expanded
 * parent's loaded children follow it; a `more` row is appended after a parent's children when
 * that parent has an unfetched next page (so both root paging and per-node child paging are a
 * single uniform affordance).
 */
export function flatten(state: TreeState): ManuscriptRow[] {
  const rows: ManuscriptRow[] = [];
  const walk = (parentKey: string, parentNodeId: string | null, depth: number) => {
    const loaded = state.childrenOf[parentKey] ?? [];
    for (const id of loaded) {
      const node = state.nodes[id];
      if (!node) continue;
      const expanded = !!state.expanded[id];
      rows.push({ type: 'node', node, depth, expanded, loading: !!state.loading[id] });
      if (expanded) walk(id, id, depth + 1);
    }
    // First-page load (nothing loaded yet) → shimmer skeletons; a parent that already has a
    // page and a further cursor → a "load more" affordance instead (its own spinner). The two
    // are mutually exclusive: you never shimmer over rows that are already on screen.
    if (loaded.length === 0 && state.loading[parentKey]) {
      rows.push({ type: 'skeleton', depth, key: `sk-${parentKey || 'root'}-0` });
      rows.push({ type: 'skeleton', depth, key: `sk-${parentKey || 'root'}-1` });
    } else if (hasMore(state, parentKey)) {
      rows.push({ type: 'more', parentKey, parentNodeId, depth });
    }
  };
  walk(ROOT_KEY, null, 0);
  return rows;
}

/** Append a page of children under `parentKey`, de-duping ids (idempotent re-fetch safe). */
export function appendChildren(
  state: TreeState,
  parentKey: string,
  nodes: ManuscriptNode[],
  nextCursor: string | null,
): TreeState {
  const nextNodes = { ...state.nodes };
  const existing = state.childrenOf[parentKey] ?? [];
  const seen = new Set(existing);
  const added: string[] = [];
  for (const n of nodes) {
    nextNodes[n.id] = n;
    if (!seen.has(n.id)) {
      added.push(n.id);
      seen.add(n.id);
    }
  }
  return {
    ...state,
    nodes: nextNodes,
    childrenOf: { ...state.childrenOf, [parentKey]: [...existing, ...added] },
    childCursor: { ...state.childCursor, [parentKey]: nextCursor },
  };
}

export function setExpanded(state: TreeState, id: string, expanded: boolean): TreeState {
  return { ...state, expanded: { ...state.expanded, [id]: expanded } };
}

export function setLoading(state: TreeState, key: string, loading: boolean): TreeState {
  return { ...state, loading: { ...state.loading, [key]: loading } };
}

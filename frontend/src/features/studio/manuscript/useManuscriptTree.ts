import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { booksApi, type Chapter } from '@/features/books/api';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { appendChildren, flatten, setExpanded, setLoading } from './tree';
import { ROOT_KEY, emptyTree, type ManuscriptNode, type TreeState } from './types';

const PAGE = 100;

/** book-service chapter → a flat chapter node (no children). */
function chapterToNode(c: Chapter): ManuscriptNode {
  return {
    id: c.chapter_id,
    kind: 'chapter',
    title: c.title || c.original_filename || `#${c.sort_order}`,
    number: c.sort_order,
    status: null,
    chapterId: c.chapter_id,
    hasChildren: false,
    childCount: null, // flat chapters carry no scene structure
  };
}

/** composition outline node → a tree node. Arcs + chapters can expand; scenes are leaves. */
function outlineToNode(n: OutlineNode): ManuscriptNode {
  const kind = n.kind === 'arc' ? 'arc' : n.kind === 'scene' ? 'scene' : 'chapter';
  const childCount = n.child_count ?? 0;
  return {
    id: n.id,
    kind,
    title: n.title || '(untitled)',
    number: null,
    status: n.status ?? null,
    chapterId: n.chapter_id,
    // Trust child_count over kind: an outlined chapter with 0 scenes has nothing to lazy-load,
    // so it's a leaf (no caret) — matches the mockup's "≤1 scene ⇒ chapter is the leaf".
    hasChildren: kind !== 'scene' && childCount > 0,
    childCount: kind === 'scene' ? null : childCount,
  };
}

export type ManuscriptSource = 'pending' | 'chapters' | 'outline';

/**
 * The manuscript tree data source. Resolves the book's composition Work: a Work → the outline
 * (arc→chapter→scene, lazy-paged via listOutlineChildren); no Work → a flat chapter list
 * (cursor-paged via listChaptersPage). Both stream into one TreeState; the view is agnostic.
 */
export function useManuscriptTree(bookId: string, token: string | null) {
  const work = useWorkResolution(bookId, token);
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  // EC-3d: the ACTIVE Work's project (per-book pref, else canonical) — NOT candidates[0].
  const projectId = useMemo(
    () => resolveActiveWork(work.data, activeWorkId)?.project_id ?? null,
    [work.data, activeWorkId],
  );

  const source: ManuscriptSource = work.isLoading ? 'pending' : projectId ? 'outline' : 'chapters';

  const [tree, setTree] = useState<TreeState>(emptyTree);
  const [total, setTotal] = useState<number | null>(null);
  const [outlineCounts, setOutlineCounts] = useState<{ arcs: number; chapters: number; scenes: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const treeRef = useRef(tree);
  treeRef.current = tree;
  // Per-key in-flight guard so a re-triggered load (scroll + click) never double-fetches.
  const inflight = useRef<Set<string>>(new Set());
  // Generation token: bumped on every book/source reset. A load that resolves AFTER a reset
  // is stale — it must not append the old book's rows into the new tree (review-impl M1).
  const genRef = useRef(0);

  const loadPage = useCallback(async (parentKey: string, parentNodeId: string | null, cursor: string | null) => {
    if (!token || inflight.current.has(parentKey)) return;
    if (source === 'outline' && !projectId) return;
    const gen = genRef.current;
    inflight.current.add(parentKey);
    setTree((t) => setLoading(t, parentKey, true));
    try {
      if (source === 'chapters') {
        const page = await booksApi.listChaptersPage(token, bookId, { cursor, limit: PAGE });
        if (genRef.current !== gen) return; // a reset landed while we awaited → drop the result
        if (page.total != null) setTotal(page.total);
        setTree((t) => appendChildren(t, parentKey, page.items.map(chapterToNode), page.next_cursor));
      } else if (source === 'outline' && projectId) {
        const page = await compositionApi.listOutlineChildren(projectId, token, { parentId: parentNodeId, cursor, limit: PAGE });
        if (genRef.current !== gen) return;
        // Keep only navigable kinds (arc/chapter/scene); structural 'beat' nodes are not shown.
        const nodes = page.items.filter((n) => n.kind !== 'beat').map(outlineToNode);
        setTree((t) => appendChildren(t, parentKey, nodes, page.next_cursor));
      }
    } catch (e) {
      if (genRef.current === gen) setError((e as Error).message);
    } finally {
      // Only touch the (current) tree if we're still the live generation — otherwise a stale
      // load would clear the NEW generation's in-flight guard / loading flag.
      if (genRef.current === gen) {
        inflight.current.delete(parentKey);
        setTree((t) => setLoading(t, parentKey, false));
      }
    }
  }, [token, bookId, source, projectId]);

  // Reset to an empty tree + reload the root page. Shared by the mount/source-change
  // effect and the manual Reload action; bumps the generation so any in-flight load from
  // the prior tree is dropped (review-impl M1 stale-guard).
  const resetAndLoadRoot = useCallback(() => {
    genRef.current += 1;
    inflight.current.clear();
    setTree(emptyTree());
    setTotal(null);
    setError(null);
    void loadPage(ROOT_KEY, null, null);
  }, [loadPage]);

  // Load the root page once the source resolves; reset on book/source change.
  useEffect(() => {
    if (source === 'pending') return;
    resetAndLoadRoot();
  }, [source, projectId, bookId, resetAndLoadRoot]);

  // Whole-book totals for the footer. Outline → one GROUP BY (arcs/chapters/scenes); the flat
  // chapters source has no scenes/arcs, so its chapter total comes from the page-1 `total`.
  useEffect(() => {
    if (source !== 'outline' || !projectId || !token) {
      setOutlineCounts(null);
      return;
    }
    let alive = true;
    compositionApi.outlineStats(projectId, token)
      .then((s) => { if (alive) setOutlineCounts(s); })
      .catch(() => { if (alive) setOutlineCounts(null); });
    return () => { alive = false; };
  }, [source, projectId, bookId, token]);

  const counts = useMemo(
    () => (source === 'outline'
      ? { arcs: outlineCounts?.arcs ?? null, chapters: outlineCounts?.chapters ?? null, scenes: outlineCounts?.scenes ?? null }
      : { arcs: null, chapters: total, scenes: null }),
    [source, outlineCounts, total],
  );

  // Collapse every expanded node back to the root level (VS Code "Collapse All"). Loaded
  // child pages stay in the store (cheap re-expand); only the expanded flags clear.
  const collapseAll = useCallback(() => {
    setTree((t) => ({ ...t, expanded: {} }));
  }, []);

  const toggleExpand = useCallback((nodeId: string) => {
    const t = treeRef.current;
    const willExpand = !t.expanded[nodeId];
    setTree((s) => setExpanded(s, nodeId, willExpand));
    // Lazy-load children the first time a node is expanded.
    if (willExpand && !(nodeId in t.childrenOf)) {
      void loadPage(nodeId, nodeId, null);
    }
  }, [loadPage]);

  const loadMore = useCallback((parentKey: string, parentNodeId: string | null) => {
    const cursor = treeRef.current.childCursor[parentKey];
    if (typeof cursor === 'string') void loadPage(parentKey, parentNodeId, cursor);
  }, [loadPage]);

  const rows = useMemo(() => flatten(tree), [tree]);

  return { source, rows, total, counts, error, toggleExpand, loadMore, collapseAll, reload: resetAndLoadRoot };
}

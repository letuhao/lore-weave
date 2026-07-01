import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { booksApi, type Chapter } from '@/features/books/api';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
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
  };
}

/** composition outline node → a tree node. Arcs + chapters can expand; scenes are leaves. */
function outlineToNode(n: OutlineNode): ManuscriptNode {
  const kind = n.kind === 'arc' ? 'arc' : n.kind === 'scene' ? 'scene' : 'chapter';
  return {
    id: n.id,
    kind,
    title: n.title || '(untitled)',
    number: null,
    status: n.status ?? null,
    chapterId: n.chapter_id,
    hasChildren: kind !== 'scene',
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
  const projectId = useMemo(() => {
    const d = work.data;
    if (d?.status === 'found') return d.work?.project_id ?? null;
    if (d?.status === 'candidates') return d.candidates[0]?.project_id ?? null;
    return null;
  }, [work.data]);

  const source: ManuscriptSource = work.isLoading ? 'pending' : projectId ? 'outline' : 'chapters';

  const [tree, setTree] = useState<TreeState>(emptyTree);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const treeRef = useRef(tree);
  treeRef.current = tree;
  // Per-key in-flight guard so a re-triggered load (scroll + click) never double-fetches.
  const inflight = useRef<Set<string>>(new Set());

  const loadPage = useCallback(async (parentKey: string, parentNodeId: string | null, cursor: string | null) => {
    if (!token || inflight.current.has(parentKey)) return;
    if (source === 'outline' && !projectId) return;
    inflight.current.add(parentKey);
    setTree((t) => setLoading(t, parentKey, true));
    try {
      if (source === 'chapters') {
        const page = await booksApi.listChaptersPage(token, bookId, { cursor, limit: PAGE });
        if (page.total != null) setTotal(page.total);
        setTree((t) => appendChildren(t, parentKey, page.items.map(chapterToNode), page.next_cursor));
      } else if (source === 'outline' && projectId) {
        const page = await compositionApi.listOutlineChildren(projectId, token, { parentId: parentNodeId, cursor, limit: PAGE });
        // Keep only navigable kinds (arc/chapter/scene); structural 'beat' nodes are not shown.
        const nodes = page.items.filter((n) => n.kind !== 'beat').map(outlineToNode);
        setTree((t) => appendChildren(t, parentKey, nodes, page.next_cursor));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      inflight.current.delete(parentKey);
      setTree((t) => setLoading(t, parentKey, false));
    }
  }, [token, bookId, source, projectId]);

  // Load the root page once the source resolves; reset on book/source change.
  useEffect(() => {
    if (source === 'pending') return;
    inflight.current.clear();
    setTree(emptyTree());
    setTotal(null);
    setError(null);
    void loadPage(ROOT_KEY, null, null);
  }, [source, projectId, bookId, loadPage]);

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

  return { source, rows, total, error, toggleExpand, loadMore };
}

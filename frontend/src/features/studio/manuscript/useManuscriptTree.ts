import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { booksApi, type Chapter } from '@/features/books/api';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { appendChildren, flatten, setExpanded, setLoading } from './tree';
import { ROOT_KEY, emptyTree, type ManuscriptNode, type TreeState } from './types';
import { partsApi, type Part } from './partsApi';
import { buildPartsTree, chapterDisplayTitle } from './partsTree';

const PAGE = 100;
// Cap for the parts grouping's whole-book chapter load (a structured book with acts is
// authored, typically hundreds of chapters). Beyond this we keep the flat paged tree.
const PARTS_MAX_PAGES = 60; // 60 × 100 = 6000 chapters

/** book-service chapter → a flat chapter node (no children). */
function chapterToNode(c: Chapter): ManuscriptNode {
  return {
    id: c.chapter_id,
    kind: 'chapter',
    // Never surface the storage filename (`editor-<uuid>.txt`) as a title — a raw filename read as
    // a chapter title in the first-run diary. Fall back to a localized "Chapter {n}" (F4).
    title: chapterDisplayTitle(c),
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
 *
 * S-02 — when a no-Work book has manuscript PARTS (acts/volumes), the flat list is replaced by a
 * two-level tree: act group headers with their chapters nested + an "Unassigned" bucket. Because
 * grouping needs every chapter's part_id up front, the whole (bounded) chapter set is loaded and
 * grouped in one shot (no per-part cursor). A book with NO parts keeps the flat paged behavior
 * exactly. The hook also exposes the part mutators (create/rename/trash act, move chapter).
 */
export function useManuscriptTree(bookId: string, token: string | null) {
  const work = useWorkResolution(bookId, token);
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  // EC-3d: the ACTIVE Work's project (per-book pref, else canonical) — NOT candidates[0].
  const projectId = useMemo(
    () => resolveActiveWork(work.data, activeWorkId)?.project_id ?? null,
    [work.data, activeWorkId],
  );

  const rawSource: ManuscriptSource = work.isLoading ? 'pending' : projectId ? 'outline' : 'chapters';
  // F11 — a book can have a Work whose outline is EMPTY (its chapters were never decomposed into the
  // plan). Reading the outline then shows "No chapters yet." and the book's real chapters VANISH from
  // the rail — reads as data loss, and the onboarding door ("Set up writing" / "Set up this book")
  // leads straight into it. When the outline root comes back empty (below), we flip to the flat
  // book-service chapters so an un-planned Work still browses its manuscript.
  const [outlineEmptyFallback, setOutlineEmptyFallback] = useState(false);
  const source: ManuscriptSource = rawSource === 'outline' && outlineEmptyFallback ? 'chapters' : rawSource;
  // Reset the fallback whenever the book or the underlying source changes (never leak it across books).
  useEffect(() => setOutlineEmptyFallback(false), [bookId, rawSource]);

  const [tree, setTree] = useState<TreeState>(emptyTree);
  const [total, setTotal] = useState<number | null>(null);
  const [outlineCounts, setOutlineCounts] = useState<{ arcs: number; chapters: number; scenes: number } | null>(null);
  const [parts, setParts] = useState<Part[]>([]); // S-02: active acts (empty ⇒ flat mode)
  const [trashedActs, setTrashedActs] = useState<Part[]>([]); // S-02b: soft-trashed acts (for the restore section)
  const [error, setError] = useState<string | null>(null);
  const treeRef = useRef(tree);
  treeRef.current = tree;
  // Per-key in-flight guard so a re-triggered load (scroll + click) never double-fetches.
  const inflight = useRef<Set<string>>(new Set());
  // Generation token: bumped on every book/source reset. A load that resolves AFTER a reset
  // is stale — it must not append the old book's rows into the new tree (review-impl M1).
  const genRef = useRef(0);

  const partsMode = source === 'chapters' && parts.length > 0;

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

  // S-02 — load EVERY chapter (bounded) then build the grouped act tree. Used when the book has
  // parts. gen guards against a stale book/source switch mid-load.
  const loadGroupedTree = useCallback(async (activeParts: Part[], gen: number) => {
    if (!token) return;
    const all: Chapter[] = [];
    let cursor: string | null = null;
    let pages = 0;
    try {
      do {
        const page = await booksApi.listChaptersPage(token, bookId, { cursor, limit: PAGE });
        if (genRef.current !== gen) return;
        all.push(...page.items);
        if (page.total != null) setTotal(page.total);
        cursor = page.next_cursor ?? null;
        pages += 1;
      } while (cursor && pages < PARTS_MAX_PAGES);
    } catch (e) {
      if (genRef.current === gen) setError((e as Error).message);
      return;
    }
    if (genRef.current !== gen) return;
    setTree(buildPartsTree(activeParts, all));
  }, [token, bookId]);

  // Reset to an empty tree + (re)load. For the chapters source, first resolve the book's parts:
  // parts present → the grouped act tree; none → the flat cursor-paged list (unchanged). Bumps the
  // generation so any in-flight load from the prior tree is dropped (review-impl M1 stale-guard).
  const resetAndLoad = useCallback(async () => {
    genRef.current += 1;
    const gen = genRef.current;
    inflight.current.clear();
    setTree(emptyTree());
    setTotal(null);
    setError(null);
    setParts([]);
    setTrashedActs([]);

    if (source === 'outline') {
      // Load the outline root ourselves (not via loadPage) so we can detect the EMPTY case: a Work
      // whose chapters were never decomposed. Empty ⇒ flip to the chapters fallback (F11) instead of
      // rendering "No chapters yet." over a book that has chapters.
      if (!projectId || !token) return;
      try {
        const page = await compositionApi.listOutlineChildren(projectId, token, { parentId: null, cursor: null, limit: PAGE });
        if (genRef.current !== gen) return;
        const nodes = page.items.filter((n) => n.kind !== 'beat').map(outlineToNode);
        if (nodes.length === 0) {
          setOutlineEmptyFallback(true); // re-runs resetAndLoad as 'chapters' (source flips)
          return;
        }
        setTree((t) => appendChildren(t, ROOT_KEY, nodes, page.next_cursor));
      } catch (e) {
        if (genRef.current === gen) setError((e as Error).message);
      }
      return;
    }
    if (source !== 'chapters') return;

    let active: Part[] = [];
    if (token) {
      try {
        // One include_trashed fetch splits into active (drives grouping) + trashed (restore section).
        const res = await partsApi.list(token, bookId, { includeTrashed: true });
        const all = res.items ?? [];
        active = all.filter((p) => p.lifecycle_state === 'active');
        if (genRef.current === gen) setTrashedActs(all.filter((p) => p.lifecycle_state === 'trashed'));
      } catch {
        active = []; // a book-service without S-02, or a transient error → flat mode
      }
    }
    if (genRef.current !== gen) return; // a reset landed while resolving parts
    if (active.length > 0) {
      setParts(active);
      await loadGroupedTree(active, gen);
    } else {
      void loadPage(ROOT_KEY, null, null); // flat
    }
  }, [source, bookId, token, loadPage, loadGroupedTree]);

  // Load once the source resolves; reset on book/source change.
  useEffect(() => {
    if (source === 'pending') return;
    void resetAndLoad();
  }, [source, projectId, bookId, resetAndLoad]);

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

  // 'arc' is an OUTLINE concept; a chapters-source book counts ACTS (parts), not arcs — the
  // footer label must not say "arc" for acts (S-02c B1). Acts are surfaced via `parts.length`.
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
    // Lazy-load children the first time a node is expanded (outline only — the parts tree and the
    // flat list are already fully loaded, so childrenOf already has the node's children).
    if (willExpand && !(nodeId in t.childrenOf)) {
      void loadPage(nodeId, nodeId, null);
    }
  }, [loadPage]);

  const loadMore = useCallback((parentKey: string, parentNodeId: string | null) => {
    const cursor = treeRef.current.childCursor[parentKey];
    if (typeof cursor === 'string') void loadPage(parentKey, parentNodeId, cursor);
  }, [loadPage]);

  // ── S-02 part mutators — call book-service, then rebuild the tree ─────────────
  // Each returns the api promise so the caller can await + surface an error; every one
  // reloads so a create/rename/trash/move is reflected immediately (server is the SoT).
  const createAct = useCallback(async (title: string) => {
    if (!token) return;
    await partsApi.create(token, bookId, title);
    await resetAndLoad();
  }, [token, bookId, resetAndLoad]);

  const renameAct = useCallback(async (partId: string, title: string) => {
    if (!token) return;
    await partsApi.rename(token, bookId, partId, title);
    await resetAndLoad();
  }, [token, bookId, resetAndLoad]);

  const trashAct = useCallback(async (partId: string) => {
    if (!token) return;
    await partsApi.archive(token, bookId, partId);
    await resetAndLoad();
  }, [token, bookId, resetAndLoad]);

  // S-02b — restore a soft-trashed act. It comes back EMPTY (S-02 sealed: restore does NOT
  // re-home the chapters it once held); the caller's copy must say so.
  const restoreAct = useCallback(async (partId: string) => {
    if (!token) return;
    await partsApi.restore(token, bookId, partId);
    await resetAndLoad();
  }, [token, bookId, resetAndLoad]);

  const moveChapterToAct = useCallback(async (chapterId: string, partId: string | null) => {
    if (!token) return;
    await partsApi.setChapterPart(token, bookId, chapterId, partId);
    await resetAndLoad();
  }, [token, bookId, resetAndLoad]);

  // S-02b — reorder acts by swapping the target with its neighbour and rewriting the whole
  // order (partsApi.reorder wants EVERY active id). Boundary move (up at top / down at bottom)
  // is a no-op. `parts` is already in sort order (the list route orders by sort_order).
  const moveAct = useCallback(async (partId: string, dir: 'up' | 'down') => {
    if (!token) return;
    const ordered = parts.map((p) => p.part_id);
    const i = ordered.indexOf(partId);
    const j = dir === 'up' ? i - 1 : i + 1;
    if (i < 0 || j < 0 || j >= ordered.length) return; // boundary → no-op
    [ordered[i], ordered[j]] = [ordered[j], ordered[i]];
    await partsApi.reorder(token, bookId, ordered);
    await resetAndLoad();
  }, [token, bookId, parts, resetAndLoad]);

  const rows = useMemo(() => flatten(tree), [tree]);

  return {
    source, rows, total, counts, error, partsMode, parts, trashedActs,
    toggleExpand, loadMore, collapseAll, reload: resetAndLoad,
    createAct, renameAct, trashAct, moveChapterToAct, moveAct, restoreAct,
  };
}

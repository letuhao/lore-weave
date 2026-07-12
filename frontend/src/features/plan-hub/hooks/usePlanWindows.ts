// Plan Hub v2 (spec 24 §H2.3 / PH11) — the keyset WINDOW loader.
// Per EXPANDED arc it keyset-pages the arc's chapter window (getChildren by structure_node_id);
// per EXPANDED chapter it keyset-pages that chapter's scene window (getChildren by parent_id).
// A COLLAPSED arc contributes NO window here — laneLayout synthesises its 'arc-rollup' card from
// the shell's chapter_count + collapse state, so this hook simply DOESN'T load a collapsed arc.
// Returns the flat WindowNode[] laneLayout consumes, plus per-arc / per-chapter loading + hasMore
// + loadMore for infinite scroll. Manual keyset state (mirrors useSceneBrowser): the set of open
// arcs/chapters is dynamic, so a per-key useInfiniteQuery would break the rules of hooks.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getChildren } from '../api';
import type { SummaryNode, WindowNode } from '../types';
import { toWindowNode } from './planHubMappers';

const CHILD_PAGE = 100; // the children route's keyset page size

/**
 * The UNASSIGNED window (PH21) rides the arc-slice machinery under a sentinel key, so it inherits
 * paging, `reload()` and `patch()` for free instead of growing a fourth parallel state shape.
 * It is a real uuid-shaped impossibility, so it can never collide with an arc id.
 *
 * It loads on EVERY book open (an arc-less chapter belongs to no arc, so no expand can reveal it),
 * but it loads in an effect — i.e. AFTER paint, like every other chapter window (PH11). The ≤5
 * cold-open budget counts the paint-blocking reads, which this is not.
 */
export const UNASSIGNED_KEY = 'unassigned:no-arc';

interface WindowSlice {
  // The raw summary rows — title/status/tension live here; laneLayout gets the WindowNode subset.
  items: SummaryNode[];
  cursor: string | null; // next_cursor of the last fetched page; null ⇒ last page reached
  loading: boolean;
}
const EMPTY_SLICE: WindowSlice = { items: [], cursor: null, loading: false };

export interface PlanWindowsResult {
  /** The flat loaded windows (expanded arcs' chapters + expanded chapters' scenes) for laneLayout. */
  windows: WindowNode[];
  /** The raw summary rows by node id (title/status/tension/…), for the canvas node cards. */
  content: Record<string, SummaryNode>;
  arcLoading: Record<string, boolean>;
  arcHasMore: Record<string, boolean>;
  /** Fetch the next chapter page of an expanded arc (infinite scroll along its lane). */
  loadMoreArc: (arcId: string) => void;
  chapterLoading: Record<string, boolean>;
  chapterHasMore: Record<string, boolean>;
  /** Fetch the next scene page of an expanded chapter's branch. */
  loadMoreChapter: (chapterId: string) => void;
  /**
   * H5 — re-fetch the FIRST page of every currently-loaded window. THE moves (chapter→lane,
   * scene→chapter) mutate `structure_node_id` / `parent_id` / `version` on rows that live in THESE
   * slices, and these slices are hand-rolled state, NOT react-query: a
   * `qc.invalidateQueries(['plan-hub'])` refreshes the arc shell but CANNOT reach them. Without this
   * the moved card keeps its pre-move lane/parent forever (the write looks silently ignored), and its
   * stale `version` 412s the very next move of the same node. Callers invoke it alongside the
   * invalidate on every move settle.
   *
   * Refetching page 1 (not every loaded page) resets a deep-scrolled lane to its first page; the
   * cursor comes back with it, so scrolling re-earns the rest. Truthful over clever.
   */
  reload: () => void;
  /**
   * H5 — OPTIMISTICALLY patch a loaded row (e.g. a chapter's `structure_node_id`, a scene's
   * `parent_id`) so laneLayout re-places the card the instant the drag ends, instead of leaving it
   * in its old slot for the round-trip + refetch (a visible snap-back-then-jump).
   *
   * This is a display-only anticipation of the server's answer, NOT a second source of truth: every
   * move still settles with `reload()`, which overwrites whatever we guessed. A failed move
   * therefore rolls itself back — we never have to undo the patch by hand.
   */
  patch: (nodeId: string, partial: Partial<SummaryNode>) => void;
  /**
   * Has the UNASSIGNED window come back yet? The PH21 empty state ("no plan — extract one?")
   * turns on "there are no chapter nodes anywhere", and with zero arcs this is the only window
   * that could hold one. Answering that question from `absent` rather than `answered` would flash
   * an offer to EXTRACT a plan over a book whose plan simply hadn't loaded — absent ≠ empty.
   */
  unassignedLoaded: boolean;
  loading: boolean;
  error: string | null;
}

function mapField<T>(slices: Record<string, WindowSlice>, f: (s: WindowSlice) => T): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [k, v] of Object.entries(slices)) out[k] = f(v);
  return out;
}

export function usePlanWindows(
  bookId: string | null,
  token: string | null,
  expandedArcIds: string[],
  expandedChapterIds: string[],
): PlanWindowsResult {
  const [arcSlices, setArcSlices] = useState<Record<string, WindowSlice>>({});
  const [chapterSlices, setChapterSlices] = useState<Record<string, WindowSlice>>({});
  const [error, setError] = useState<string | null>(null);
  // Set ONLY when the unassigned window comes back SUCCESSFULLY. A failed fetch leaves it false:
  // a failure means we do not KNOW whether the book has un-filed chapters, and "don't know" must
  // not read as "there are none" (which would offer to extract a plan that may already exist).
  const [unassignedLoaded, setUnassignedLoaded] = useState(false);

  // Generation guard: a page that resolves after a book switch must not clobber newer state.
  const gen = useRef(0);
  // First-page-fired guard: auto-load a newly-expanded window exactly once (loadMore drives the
  // rest). Cleared on a book change so the new book re-fires. NOT cleared on collapse/re-expand —
  // the cached slice is still valid, so re-opening an arc reuses it without a refetch.
  const requestedArcs = useRef<Set<string>>(new Set());
  const requestedChapters = useRef<Set<string>>(new Set());

  useEffect(() => {
    gen.current += 1;
    requestedArcs.current = new Set();
    requestedChapters.current = new Set();
    setArcSlices({});
    setChapterSlices({});
    setError(null);
    setUnassignedLoaded(false);
  }, [bookId]);

  const fetchArc = useCallback(
    async (arcId: string, cursor: string | null) => {
      if (!token || !bookId) return;
      const myGen = gen.current;
      setArcSlices((prev) => ({ ...prev, [arcId]: { ...(prev[arcId] ?? EMPTY_SLICE), loading: true } }));
      try {
        const axis =
          arcId === UNASSIGNED_KEY ? ({ unassigned: true } as const) : { structureNodeId: arcId };
        const page = await getChildren(bookId, axis, { cursor, limit: CHILD_PAGE, token });
        if (myGen !== gen.current) return;
        setArcSlices((prev) => {
          const cur = prev[arcId] ?? EMPTY_SLICE;
          return {
            ...prev,
            [arcId]: { items: cursor ? [...cur.items, ...page.items] : page.items, cursor: page.next_cursor, loading: false },
          };
        });
        if (arcId === UNASSIGNED_KEY) setUnassignedLoaded(true);
      } catch (e) {
        if (myGen !== gen.current) return;
        setError(e instanceof Error ? e.message : 'Failed to load chapters');
        setArcSlices((prev) => ({ ...prev, [arcId]: { ...(prev[arcId] ?? EMPTY_SLICE), loading: false } }));
      }
    },
    [token, bookId],
  );

  const fetchChapter = useCallback(
    async (chapterId: string, cursor: string | null) => {
      if (!token || !bookId) return;
      const myGen = gen.current;
      setChapterSlices((prev) => ({ ...prev, [chapterId]: { ...(prev[chapterId] ?? EMPTY_SLICE), loading: true } }));
      try {
        const page = await getChildren(bookId, { parentId: chapterId }, { cursor, limit: CHILD_PAGE, token });
        if (myGen !== gen.current) return;
        setChapterSlices((prev) => {
          const cur = prev[chapterId] ?? EMPTY_SLICE;
          return {
            ...prev,
            [chapterId]: { items: cursor ? [...cur.items, ...page.items] : page.items, cursor: page.next_cursor, loading: false },
          };
        });
      } catch (e) {
        if (myGen !== gen.current) return;
        setError(e instanceof Error ? e.message : 'Failed to load scenes');
        setChapterSlices((prev) => ({ ...prev, [chapterId]: { ...(prev[chapterId] ?? EMPTY_SLICE), loading: false } }));
      }
    },
    [token, bookId],
  );

  // Auto-load the first page of each newly-expanded arc / chapter (synchronisation, not an event).
  // The UNASSIGNED window is always in this set: its chapters hang off no arc, so no expand gesture
  // could ever request them — without this they are simply never fetched and the strip renders
  // empty on a book whose plan is entirely un-filed (exactly the post-decompile state).
  useEffect(() => {
    if (!token || !bookId) return;
    for (const arcId of [UNASSIGNED_KEY, ...expandedArcIds]) {
      if (!requestedArcs.current.has(arcId)) {
        requestedArcs.current.add(arcId);
        void fetchArc(arcId, null);
      }
    }
  }, [expandedArcIds, token, bookId, fetchArc]);

  useEffect(() => {
    if (!token || !bookId) return;
    for (const chapterId of expandedChapterIds) {
      if (!requestedChapters.current.has(chapterId)) {
        requestedChapters.current.add(chapterId);
        void fetchChapter(chapterId, null);
      }
    }
  }, [expandedChapterIds, token, bookId, fetchChapter]);

  const loadMoreArc = useCallback(
    (arcId: string) => {
      const slice = arcSlices[arcId];
      if (slice?.cursor && !slice.loading) void fetchArc(arcId, slice.cursor);
    },
    [arcSlices, fetchArc],
  );

  const loadMoreChapter = useCallback(
    (chapterId: string) => {
      const slice = chapterSlices[chapterId];
      if (slice?.cursor && !slice.loading) void fetchChapter(chapterId, slice.cursor);
    },
    [chapterSlices, fetchChapter],
  );

  // Which windows are loaded RIGHT NOW, for reload(). A ref (not the state) so `reload` keeps a
  // stable identity — it lands in the move mutations' onSettled, and a new identity there would
  // re-create every mutation on each page load.
  const loadedRef = useRef<{ arcs: string[]; chapters: string[] }>({ arcs: [], chapters: [] });
  useEffect(() => {
    loadedRef.current = { arcs: Object.keys(arcSlices), chapters: Object.keys(chapterSlices) };
  }, [arcSlices, chapterSlices]);

  const reload = useCallback(() => {
    for (const arcId of loadedRef.current.arcs) void fetchArc(arcId, null);
    for (const chapterId of loadedRef.current.chapters) void fetchChapter(chapterId, null);
  }, [fetchArc, fetchChapter]);

  const patch = useCallback((nodeId: string, partial: Partial<SummaryNode>) => {
    const apply = (slices: Record<string, WindowSlice>) => {
      let touched = false;
      const next: Record<string, WindowSlice> = {};
      for (const [key, slice] of Object.entries(slices)) {
        const i = slice.items.findIndex((it) => it.id === nodeId);
        if (i < 0) {
          next[key] = slice;
          continue;
        }
        const items = [...slice.items];
        items[i] = { ...items[i], ...partial };
        next[key] = { ...slice, items };
        touched = true;
      }
      return touched ? next : slices; // identity-stable when the node isn't loaded here
    };
    setArcSlices(apply);
    setChapterSlices(apply);
  }, []);

  const windows = useMemo(() => {
    const out: WindowNode[] = [];
    for (const s of Object.values(arcSlices)) out.push(...s.items.map(toWindowNode));
    for (const s of Object.values(chapterSlices)) out.push(...s.items.map(toWindowNode));
    return out;
  }, [arcSlices, chapterSlices]);

  // The raw summary content by node id (title/status/tension/beat_role/chapter_id) — the canvas
  // node cards read titles from here (NodePosition is layout-only). Chapter/scene ids never
  // collide (distinct outline_node ids), so one flat map is safe.
  const content = useMemo(() => {
    const out: Record<string, SummaryNode> = {};
    for (const s of Object.values(arcSlices)) for (const it of s.items) out[it.id] = it;
    for (const s of Object.values(chapterSlices)) for (const it of s.items) out[it.id] = it;
    return out;
  }, [arcSlices, chapterSlices]);

  const arcLoading = useMemo(() => mapField(arcSlices, (s) => s.loading), [arcSlices]);
  const arcHasMore = useMemo(() => mapField(arcSlices, (s) => s.cursor != null), [arcSlices]);
  const chapterLoading = useMemo(() => mapField(chapterSlices, (s) => s.loading), [chapterSlices]);
  const chapterHasMore = useMemo(() => mapField(chapterSlices, (s) => s.cursor != null), [chapterSlices]);
  const loading = useMemo(
    () =>
      Object.values(arcSlices).some((s) => s.loading) || Object.values(chapterSlices).some((s) => s.loading),
    [arcSlices, chapterSlices],
  );

  return {
    windows,
    content,
    arcLoading,
    arcHasMore,
    loadMoreArc,
    chapterLoading,
    chapterHasMore,
    loadMoreChapter,
    reload,
    patch,
    unassignedLoaded,
    loading,
    error,
  };
}

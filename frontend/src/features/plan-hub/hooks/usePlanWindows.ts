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
  }, [bookId]);

  const fetchArc = useCallback(
    async (arcId: string, cursor: string | null) => {
      if (!token || !bookId) return;
      const myGen = gen.current;
      setArcSlices((prev) => ({ ...prev, [arcId]: { ...(prev[arcId] ?? EMPTY_SLICE), loading: true } }));
      try {
        const page = await getChildren(bookId, { structureNodeId: arcId }, { cursor, limit: CHILD_PAGE, token });
        if (myGen !== gen.current) return;
        setArcSlices((prev) => {
          const cur = prev[arcId] ?? EMPTY_SLICE;
          return {
            ...prev,
            [arcId]: { items: cursor ? [...cur.items, ...page.items] : page.items, cursor: page.next_cursor, loading: false },
          };
        });
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
  useEffect(() => {
    if (!token || !bookId) return;
    for (const arcId of expandedArcIds) {
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
    loading,
    error,
  };
}

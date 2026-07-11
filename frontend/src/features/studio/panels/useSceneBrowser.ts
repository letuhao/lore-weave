// 22-C2 controller — the scene-browser's logic + state (no JSX). Resolves the book's Work,
// fetches the book-service scene index + the composition spec, and joins them into the union
// rows the view renders. A Work-LESS book (never opened in the composer) is a first-class
// state: the identity side still renders (all index_only rows) with a "create a plan" CTA —
// this is exactly the empty-rail bug fixed at the root (spec 22 §F1 / §GUI state ②).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Scene } from '@/features/books/api';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { joinSceneRows, filterUnionRows, type SceneUnionRow } from './sceneUnion';

const SCENE_PAGE = 100; // book-service clamps limit to 100; page at the clamp

export type SceneBrowserState = {
  rows: SceneUnionRow[];
  loading: boolean;
  error: string | null;
  workless: boolean; // no composition Work → intent columns render as "needs a plan"
  projectId: string | null;
  total: number | null;
  hasMore: boolean;
  query: string;
  setQuery: (q: string) => void;
  loadMore: () => void;
  reload: () => void;
};

export function useSceneBrowser(bookId: string | null): SceneBrowserState {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const work = useWorkResolution(bookId ?? '', token);

  const projectId = useMemo(() => {
    const d = work.data;
    if (d?.status === 'found') return d.work?.project_id ?? null;
    if (d?.status === 'candidates') return d.candidates[0]?.project_id ?? null;
    return null;
  }, [work.data]);
  // "Work-less" is only true once resolution has SETTLED without a project — while it is still
  // loading we are not yet workless (avoids a flash of the empty-state CTA on every open).
  const workless = !work.isLoading && !projectId;

  const [scenes, setScenes] = useState<Scene[]>([]);
  const [specNodes, setSpecNodes] = useState<OutlineNode[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  // Generation guard: a load that resolves after a book/Work switch must not clobber newer state.
  const gen = useRef(0);

  // Reset when the book or its resolved Work changes.
  useEffect(() => {
    gen.current += 1;
    setScenes([]); setSpecNodes([]); setCursor(null); setTotal(null); setError(null);
  }, [bookId, projectId]);

  const fetchScenePage = useCallback(async (nextCursor: string | null) => {
    if (!token || !bookId) return;
    const myGen = ++gen.current;
    setLoading(true);
    setError(null);
    try {
      // Identity side (book-service). Also load the whole spec ONCE (first page only) so
      // spec_only rows ("planned, not written") appear — the spec is arcs/chapters/scenes,
      // tens–hundreds for a normal book; windowed spec paging is the C2b follow-up.
      const [page, outline] = await Promise.all([
        booksApi.listScenes(token, bookId, { cursor: nextCursor, limit: SCENE_PAGE }),
        !nextCursor && projectId ? compositionApi.getOutline(projectId, token) : Promise.resolve(null),
      ]);
      if (myGen !== gen.current) return; // a newer load/reset won
      setScenes((prev) => (nextCursor ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      if (page.total != null) setTotal(page.total);
      if (outline) setSpecNodes(outline.nodes);
    } catch (e) {
      if (myGen !== gen.current) return;
      setError(e instanceof Error ? e.message : 'Failed to load scenes');
    } finally {
      if (myGen === gen.current) setLoading(false);
    }
  }, [token, bookId, projectId]);

  // Initial load once resolution has settled (projectId known, or confirmed workless).
  useEffect(() => {
    if (!token || !bookId || work.isLoading) return;
    void fetchScenePage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, bookId, projectId, work.isLoading]);

  const rows = useMemo(
    () => filterUnionRows(joinSceneRows(scenes, specNodes), query),
    [scenes, specNodes, query],
  );

  const loadMore = useCallback(() => {
    if (cursor && !loading) void fetchScenePage(cursor);
  }, [cursor, loading, fetchScenePage]);

  const reload = useCallback(() => { void fetchScenePage(null); }, [fetchScenePage]);

  return {
    rows, loading, error, workless, projectId, total,
    hasMore: cursor != null, query, setQuery, loadMore, reload,
  };
}

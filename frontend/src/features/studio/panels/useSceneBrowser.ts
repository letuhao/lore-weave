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
import { useQualityWork } from './useQualityWork';
import { joinSceneRows, filterUnionRows, type SceneUnionRow } from './sceneUnion';

const SCENE_PAGE = 100; // book-service clamps limit to 100; page at the clamp

export type SceneBrowserState = {
  rows: SceneUnionRow[];
  loading: boolean;
  ready: boolean; // work resolution settled AND the first scene load has run — gates the empty state
  error: string | null; // a BLOCKING failure (the identity read failed) — the panel can't render
  intentUnavailable: boolean; // the intent side (composition) is unreachable; identity rows still render
  workless: boolean; // settled with NO composition Work → intent columns render as "needs a plan"
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
  // Distinguish a genuine no-plan resolution from a TRANSIENT backend outage: `unavailable` is NOT
  // "no plan yet", so it must not show the create-plan CTA (a user could make a duplicate Work).
  // Both settle without a projectId, so gate on the STATUS, not just projectId.
  //
  // That reasoning — first written here — is now `useQualityWork`, the ONE gate. This hook was its
  // only correct implementation; the quality panels each re-derived it and got `candidates` wrong.
  // Three copies of one rule is what SDK-First exists to stop, so this adopts the shared gate.
  const work = useQualityWork(bookId ?? '', token);
  const projectId = work.kind === 'ready' ? work.projectId : null;
  const workUnavailable = work.kind === 'unavailable';
  const workless = work.kind === 'no-work';
  const workLoading = work.kind === 'loading';

  const [scenes, setScenes] = useState<Scene[]>([]);
  const [specNodes, setSpecNodes] = useState<OutlineNode[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false); // first fetch (success OR fail) has settled
  const [error, setError] = useState<string | null>(null);
  const [intentUnavailable, setIntentUnavailable] = useState(false);
  const [query, setQuery] = useState('');
  // Generation guard: a load that resolves after a book/Work switch must not clobber newer state.
  const gen = useRef(0);

  // Reset when the book or its resolved Work changes.
  useEffect(() => {
    gen.current += 1;
    setScenes([]); setSpecNodes([]); setCursor(null); setTotal(null);
    setError(null); setIntentUnavailable(false); setInitialized(false);
  }, [bookId, projectId]);

  const fetchScenePage = useCallback(async (nextCursor: string | null) => {
    if (!token || !bookId) return;
    const myGen = ++gen.current;
    setLoading(true);
    setError(null);
    // Identity and intent are fetched INDEPENDENTLY (allSettled): the panel's headline promise is
    // that book-service identity rows ALWAYS render, even when composition is down. A whole spec
    // load (first page only) supplies spec_only rows; the index side keyset-pages. An intent-side
    // failure must degrade to null intent, never blank the identity rows the panel exists to show.
    const [pageRes, outlineRes] = await Promise.allSettled([
      booksApi.listScenes(token, bookId, { cursor: nextCursor, limit: SCENE_PAGE }),
      !nextCursor && projectId ? compositionApi.getOutline(projectId, token) : Promise.resolve(null),
    ]);
    if (myGen !== gen.current) return; // a newer load/reset won
    if (pageRes.status === 'fulfilled') {
      const page = pageRes.value;
      setScenes((prev) => (nextCursor ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      if (page.total != null) setTotal(page.total);
    } else {
      // The identity read failed — this IS blocking (there is nothing to render).
      setError(pageRes.reason instanceof Error ? pageRes.reason.message : 'Failed to load scenes');
    }
    if (outlineRes.status === 'fulfilled') {
      if (outlineRes.value) setSpecNodes(outlineRes.value.nodes);
      setIntentUnavailable(false);
    } else {
      // Intent-side failure: keep the identity rows, flag intent as unavailable (soft).
      setIntentUnavailable(true);
    }
    setLoading(false);
    setInitialized(true);
  }, [token, bookId, projectId]);

  // Initial load once resolution has settled (projectId known, or confirmed workless).
  useEffect(() => {
    if (!token || !bookId || workLoading) return;
    void fetchScenePage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, bookId, projectId, workLoading]);

  // `specComplete` is true only when every index page is loaded (cursor exhausted). Until then a
  // spec whose index scene is on an unloaded page would be misread as "not yet written" — so the
  // join suppresses spec_only rows while more pages remain (HIGH-fix). For a normal ≤100-scene
  // book the first page exhausts the cursor, so spec_only appears immediately.
  const specComplete = cursor == null && initialized;
  const rows = useMemo(
    () => filterUnionRows(joinSceneRows(scenes, specNodes, specComplete), query),
    [scenes, specNodes, specComplete, query],
  );

  const loadMore = useCallback(() => {
    if (cursor && !loading) void fetchScenePage(cursor);
  }, [cursor, loading, fetchScenePage]);

  const reload = useCallback(() => { void fetchScenePage(null); }, [fetchScenePage]);

  // Empty state is honest only once resolution has settled AND the first load has run — otherwise
  // "No scenes match" flashes for the whole Work-resolution RTT (loading is still false then).
  const ready = !workLoading && (initialized || workless || workUnavailable);

  return {
    rows, loading, ready, error, intentUnavailable, workless, projectId, total,
    hasMore: cursor != null, query, setQuery, loadMore, reload,
  };
}

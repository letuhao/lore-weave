// Plan Hub v2 (spec 24 §H2.5 / PH12) — the MANUSCRIPT half of the two-truths join.
// Reads book-service read surface #5 (`GET /v1/books/{book_id}/scenes`, verified present:
// server.go `r.Get("/scenes", s.getBookScenes)`) and derives the set of SPEC scene-node ids that
// have a written manuscript scene (via `source_scene_id`). The full spec-vs-manuscript verdict is
// assembled in usePlanHub, which owns the loaded spec nodes; this hook owns only what the
// manuscript side can prove. Reuses `booksApi.listScenes` (the established cross-feature read
// pattern, e.g. studio/panels/useSceneBrowser) rather than duplicating the route contract.
//
// It pages the WHOLE index and exposes `complete`: a not-yet-loaded manuscript scene must never be
// read as "planned-only" (the paged-join-mislabels-absent bug class), so usePlanHub gates the
// planned-only verdict on `complete`. A failed/partial read leaves `complete=false` (absent ≠ written).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { booksApi } from '@/features/books/api';
import type { ActualScene } from '../types';
import { toActualScene } from './planHubMappers';

const SCENE_PAGE = 100; // book-service clamps limit to 100; page at the clamp

export interface ActualStateResult {
  /** SPEC scene-node ids that have >=1 manuscript scene pointing at them (source_scene_id). */
  writtenNodeIds: Set<string>;
  /** All loaded manuscript scenes (identity truth), for the caller's tray/debug needs. */
  scenes: ActualScene[];
  /** Every manuscript page has loaded — gates the 'planned-only' verdict (absent ≠ written). */
  complete: boolean;
  loading: boolean;
  /**
   * The read FAILED. This is not cosmetic: on failure `complete` stays false, so `computeUnionState`
   * emits no verdicts and EVERY node renders neutral — the whole three-state treatment (written /
   * not-yet-written / anchor-lost) silently evaporates and the canvas looks like a book with nothing
   * written in it. The caller MUST surface this; a degraded join that says nothing is indistinguish-
   * able from a healthy one, which is the `silent-success-is-a-bug` class from the reader's side.
   */
  error: string | null;
}

export function useActualState(bookId: string | null, token: string | null): ActualStateResult {
  const [scenes, setScenes] = useState<ActualScene[]>([]);
  const [complete, setComplete] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gen = useRef(0);

  const load = useCallback(async () => {
    if (!token || !bookId) {
      setScenes([]);
      setComplete(false);
      return;
    }
    const myGen = ++gen.current;
    setLoading(true);
    setError(null);
    setComplete(false);
    setScenes([]);
    try {
      let cursor: string | null = null;
      const acc: ActualScene[] = [];
      // Page the whole index so `writtenNodeIds` is exhaustive before we let planned-only fire.
      do {
        const page = await booksApi.listScenes(token, bookId, { cursor, limit: SCENE_PAGE });
        if (myGen !== gen.current) return; // a newer book/reload won
        for (const s of page.items) acc.push(toActualScene(s));
        cursor = page.next_cursor;
        setScenes([...acc]); // surface incrementally; verdict still gated on `complete`
      } while (cursor);
      if (myGen !== gen.current) return;
      setComplete(true);
    } catch (e) {
      if (myGen !== gen.current) return;
      // Advisory surface: a failure must not break the canvas. Leave complete=false so no spec node
      // is falsely marked planned-only from a partial/empty read.
      setError(e instanceof Error ? e.message : 'scenes unavailable');
    } finally {
      if (myGen === gen.current) setLoading(false);
    }
  }, [token, bookId]);

  useEffect(() => {
    void load();
  }, [load]);

  const writtenNodeIds = useMemo(() => {
    const s = new Set<string>();
    for (const sc of scenes) if (sc.source_scene_id) s.add(sc.source_scene_id);
    return s;
  }, [scenes]);

  return { writtenNodeIds, scenes, complete, loading, error };
}

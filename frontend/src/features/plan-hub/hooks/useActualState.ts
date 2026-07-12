// Plan Hub v2 (spec 24 §H2.5 / PH12) — the MANUSCRIPT half of the two-truths join.
//
// Reads book-service read surface #5 (`GET /v1/books/{book_id}/scenes`, `chapter_id`-filtered) and
// derives the set of SPEC scene-node ids that have a written manuscript scene (via `source_scene_id`).
// The full spec-vs-manuscript verdict is assembled in usePlanHub, which owns the loaded spec nodes.
//
// LAZY, PER LOADED CHAPTER — this is H8.1's budget, not a preference.
// The first cut paged the WHOLE book's scene index on mount. Read surface #5's contract is explicit
// that actual-state "fetches lazily per loaded window" (24 §Load sequence step 3), and PH9 caps the
// cold open at 5 requests. On a 10k-chapter book the eager version issued ~100 sequential pages
// before the join could settle — a budget violation by two orders of magnitude, on the one read that
// is supposed to trail the paint.
//
// COMPLETENESS IS PER CHAPTER, and it gates the verdict. A spec scene node may only be called
// "planned-only" (i.e. NOT written) once ITS OWN chapter's manuscript scenes are fully read. While a
// chapter is still paging, its scenes get NO entry and render neutrally — a not-yet-loaded scene
// declared "not written" is the `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent`
// bug, and it would paint a finished book as unwritten.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { booksApi } from '@/features/books/api';
import type { ActualScene } from '../types';
import { toActualScene } from './planHubMappers';

const SCENE_PAGE = 100; // book-service clamps limit to 100; page at the clamp
const MAX_PAGES = 50;   // 5000 scenes in ONE chapter is not a real book; bound the walk

export interface ActualStateResult {
  /** SPEC scene-node ids that have >=1 manuscript scene pointing at them (source_scene_id). */
  writtenNodeIds: Set<string>;
  /** BOOK chapter ids whose manuscript scenes are FULLY read. A spec scene may only be judged
   *  "planned-only" when its own chapter is in here (absent ≠ not-written). */
  completeChapters: Set<string>;
  /** All loaded manuscript scenes (identity truth), for the caller's tray/debug needs. */
  scenes: ActualScene[];
  loading: boolean;
  /**
   * The read FAILED. Not cosmetic: without it the affected chapters never complete, so
   * `computeUnionState` emits no verdicts for their scenes and every card renders neutral — the
   * three-state treatment silently evaporates and a written book looks unwritten. The caller MUST
   * surface this (usePlanHub puts it in `notices`).
   */
  error: string | null;
}

export function useActualState(
  bookId: string | null,
  token: string | null,
  /** The BOOK chapter ids whose spec windows are currently loaded. Only these are fetched. */
  chapterIds: string[],
): ActualStateResult {
  const [byChapter, setByChapter] = useState<Record<string, ActualScene[]>>({});
  const [completeChapters, setCompleteChapters] = useState<Set<string>>(() => new Set());
  const [loadingCount, setLoadingCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Generation guard: a page that resolves after a book switch must not clobber newer state.
  const gen = useRef(0);
  // Fetch each chapter's scenes exactly once (a re-render with the same loaded set must not refetch).
  const requested = useRef<Set<string>>(new Set());

  useEffect(() => {
    gen.current += 1;
    requested.current = new Set();
    setByChapter({});
    setCompleteChapters(new Set());
    setError(null);
    // The in-flight counter must reset too: the `finally` below SKIPS its decrement for a stale
    // generation, so a book switch mid-flight would otherwise leak the count and pin `loading`
    // true forever.
    setLoadingCount(0);
  }, [bookId]);

  const fetchChapter = useCallback(
    async (chapterId: string) => {
      if (!token || !bookId) return;
      const myGen = gen.current;
      setLoadingCount((n) => n + 1);
      try {
        let cursor: string | null = null;
        const acc: ActualScene[] = [];
        for (let page = 0; page < MAX_PAGES; page++) {
          const res = await booksApi.listScenes(token, bookId, {
            cursor,
            limit: SCENE_PAGE,
            chapter_id: chapterId,
          });
          if (myGen !== gen.current) return;
          for (const s of res.items) acc.push(toActualScene(s));
          cursor = res.next_cursor;
          if (!cursor) break;
        }
        if (myGen !== gen.current) return;
        setByChapter((prev) => ({ ...prev, [chapterId]: acc }));
        // Mark complete ONLY on a clean full read — this is what licenses a "planned-only" verdict.
        setCompleteChapters((prev) => new Set(prev).add(chapterId));
      } catch (e) {
        if (myGen !== gen.current) return;
        // Leave the chapter INCOMPLETE: no scene of it may be judged not-written from a failed read.
        setError(e instanceof Error ? e.message : 'scenes unavailable');
        // …and make it RETRYABLE. `requested` is what stops a re-fetch, so a transient failure would
        // otherwise strand this chapter as permanently-unknown for the whole session: collapse and
        // re-expand would not retry, and its scenes would render neutral forever — the three-state
        // treatment quietly evaporating, which is the exact thing this file's header forbids.
        requested.current.delete(chapterId);
      } finally {
        if (myGen === gen.current) setLoadingCount((n) => Math.max(0, n - 1));
      }
    },
    [token, bookId],
  );

  // Synchronisation (not event-handling): fetch each newly-loaded chapter's manuscript scenes once.
  useEffect(() => {
    if (!token || !bookId) return;
    for (const chapterId of chapterIds) {
      if (!chapterId || requested.current.has(chapterId)) continue;
      requested.current.add(chapterId);
      void fetchChapter(chapterId);
    }
  }, [chapterIds, token, bookId, fetchChapter]);

  const scenes = useMemo(() => Object.values(byChapter).flat(), [byChapter]);

  const writtenNodeIds = useMemo(() => {
    const s = new Set<string>();
    for (const sc of scenes) if (sc.source_scene_id) s.add(sc.source_scene_id);
    return s;
  }, [scenes]);

  return { writtenNodeIds, completeChapters, scenes, loading: loadingCount > 0, error };
}

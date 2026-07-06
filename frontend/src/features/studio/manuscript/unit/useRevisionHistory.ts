// #16 Phase 1, task 1.3 — Revision History for the Studio EditorPanel. Thin controller over
// the existing booksApi.listRevisions/restoreRevision REST (Tier-5, unchanged from the legacy
// `RevisionHistory.tsx` this replaces — no fork). Restore is G7-guarded: it refuses to touch
// the server OR the hoist while the active chapter is dirty. Restoring server-side and then
// reloading (ManuscriptUnitProvider.reload()) would silently discard unsaved keystrokes — the
// exact class of bug G7 exists to prevent for the Lane-B reconciler (bookEffects.ts's
// bookDraftEffect: `if (ctx.isChapterDirty?.(chapterId)) return;`). A revision restore is just
// another reload-capable call site of the same rule, so it calls the SAME
// `ManuscriptUnitApi.isChapterDirty` check the reconciler already uses — not a new mechanism.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import type { ManuscriptUnitApi } from './ManuscriptUnitProvider';

export interface Revision {
  revision_id: string;
  created_at: string;
  message?: string;
}

export type RestoreResult =
  | { ok: true }
  | { ok: false; reason: 'dirty' | 'no-chapter' | 'error'; message?: string };

const PAGE_SIZE = 20;

/**
 * @param unit The Tier-4 manuscript hoist (from `useManuscriptUnit()`), or null when the panel
 *   renders before the provider mounts (tests / a transient frame) — every action below no-ops
 *   safely without it.
 * @param bookId The active book (same value the panel already has via `useStudioHost()`).
 */
export function useRevisionHistory(unit: ManuscriptUnitApi | null, bookId: string) {
  const { accessToken } = useAuth();
  const chapterId = unit?.state.chapterId ?? null;

  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  // Set when a restore was refused because the hoist is dirty — the UI surfaces this instead of
  // silently doing nothing (no-silent-no-op) or clobbering the unsaved edit.
  const [blocked, setBlocked] = useState<{ revisionId: string; reason: 'dirty' } | null>(null);

  const fetchPage = useCallback(async (offset: number) => {
    if (!accessToken || !chapterId) return;
    const r = await booksApi.listRevisions(accessToken, bookId, chapterId, { limit: PAGE_SIZE, offset });
    setTotal(r.total);
    setRevisions((prev) => (offset === 0 ? r.items : [...prev, ...r.items]));
  }, [accessToken, bookId, chapterId]);

  const refresh = useCallback(async () => {
    if (!accessToken || !chapterId) {
      setRevisions([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await fetchPage(0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [accessToken, chapterId, fetchPage]);

  // Re-list whenever the active chapter changes OR `state.version` bumps. /review-impl cross-hook
  // finding: the sibling #16 1.2 `useManuscriptCheckpoints` hook can ALSO restore this same
  // chapter (a different hook instance, same chapter_revision spine) — without watching version,
  // a Checkpoints-triggered restore left this list stale until the user happened to switch
  // chapters. Combined into ONE effect (not two separate chapterId/version watchers) keyed on
  // both together, so a chapter switch that ALSO changes version (the normal case) fires exactly
  // once, not twice — `restore()` below relies on this to refresh, so it doesn't call refresh()
  // itself (would otherwise double-fetch on top of this effect).
  const version = unit?.state.version;
  const prevKeyRef = useRef<string | null>(null);
  useEffect(() => {
    const key = chapterId ? `${chapterId}:${version ?? ''}` : null;
    if (key !== prevKeyRef.current) {
      prevKeyRef.current = key;
      void refresh();
    }
  }, [chapterId, version, refresh]);

  // The dirty-block banner is stale once the hoist becomes clean again (e.g. the user saved) —
  // clear it so a later restore attempt isn't shadowed by a leftover message.
  useEffect(() => {
    if (blocked && chapterId && !unit?.isChapterDirty(chapterId)) setBlocked(null);
  }, [unit?.isDirty, chapterId, blocked, unit]);

  const loadMore = useCallback(async () => {
    if (loadingMore || revisions.length >= total) return;
    setLoadingMore(true);
    try {
      await fetchPage(revisions.length);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }, [fetchPage, loadingMore, revisions.length, total]);

  const restore = useCallback(async (revisionId: string): Promise<RestoreResult> => {
    if (!accessToken || !chapterId) return { ok: false, reason: 'no-chapter' };
    // G7 — refuse the WHOLE action (not just the reload) while dirty. Restoring server-side and
    // leaving the local buffer dirty would let the next auto/manual save silently undo the
    // restore behind the writer's back; blocking up front is the only safe option here (no
    // override — the caller must save or discard first).
    if (unit?.isChapterDirty(chapterId)) {
      setBlocked({ revisionId, reason: 'dirty' });
      return { ok: false, reason: 'dirty' };
    }
    setBlocked(null);
    setRestoringId(revisionId);
    setError(null);
    try {
      await booksApi.restoreRevision(accessToken, bookId, chapterId, revisionId);
      // Reuse the hoist's OWN load machinery — reload() re-fetches the draft and pushes it into
      // loadedBody/version exactly like openUnit does. No parallel state-update path. The bumped
      // version is picked up by the chapterId+version effect above (not an explicit refresh()
      // here) — the same mechanism a SIBLING hook's restore relies on, so there's one refresh path
      // for every trigger instead of two racing ones.
      await unit?.reload();
      return { ok: true };
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      return { ok: false, reason: 'error', message };
    } finally {
      setRestoringId(null);
    }
  }, [accessToken, bookId, chapterId, unit, refresh]);

  const clearBlocked = useCallback(() => setBlocked(null), []);

  return {
    revisions,
    total,
    hasMore: revisions.length < total,
    loading,
    loadingMore,
    error,
    restoringId,
    blocked,
    refresh,
    loadMore,
    restore,
    clearBlocked,
  };
}

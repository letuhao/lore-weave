// RAID C6 — turn checkpoints: an AI-edit-AWARE layer over the existing chapter
// revision spine (book-service snapshots a chapter_revision on every draft
// PATCH). Every autosave makes a revision, so RevisionHistory shows an
// undifferentiated wall of them; C6 marks the revision that was current
// *before* each AI edit so the writer can restore to "before the agent touched
// it" in one click. The durable truth stays the server-side revisions — this
// list is just a curated in-editor view of restore points (server-is-SoT).
import { useCallback, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';

export interface TurnCheckpoint {
  id: string;
  chapterId: string;
  /** The latest revision id BEFORE this AI edit landed = the restore point.
   * null when the chapter had no revisions yet (nothing to restore to). */
  preRevisionId: string | null;
  at: number;
  snippet: string;
  /** Consecutive AI edits sharing the same pre-revision fold into one (no
   * autosave committed between them → restoring any is the same rollback). */
  count: number;
  kind: 'insert' | 'polish';
}

const MAX_CHECKPOINTS = 20;

export function useTurnCheckpoints(bookId: string) {
  const { accessToken } = useAuth();
  const [checkpoints, setCheckpoints] = useState<TurnCheckpoint[]>([]);

  // Called at the AI-apply seam BEFORE the edit mutates the draft, so the
  // captured "latest revision" is the pre-edit state.
  const capture = useCallback(
    async (chapterId: string, snippet: string, kind: 'insert' | 'polish') => {
      if (!accessToken || !chapterId) return;
      let preRevisionId: string | null = null;
      try {
        const r = await booksApi.listRevisions(accessToken, bookId, chapterId, { limit: 1, offset: 0 });
        preRevisionId = r.items[0]?.revision_id ?? null;
      } catch {
        /* no revisions yet / offline → null restore point (Restore disabled) */
      }
      setCheckpoints((prev) => {
        const last = prev[0];
        if (last && last.chapterId === chapterId && last.preRevisionId === preRevisionId) {
          const folded: TurnCheckpoint = { ...last, count: last.count + 1, snippet: snippet.slice(0, 80), at: Date.now() };
          return [folded, ...prev.slice(1)];
        }
        const cp: TurnCheckpoint = {
          id: `${chapterId}:${Date.now()}:${Math.random().toString(36).slice(2, 6)}`,
          chapterId, preRevisionId, at: Date.now(), snippet: snippet.slice(0, 80), count: 1, kind,
        };
        return [cp, ...prev].slice(0, MAX_CHECKPOINTS);
      });
    },
    [accessToken, bookId],
  );

  const restore = useCallback(
    async (cp: TurnCheckpoint) => {
      if (!accessToken || !cp.preRevisionId) return;
      await booksApi.restoreRevision(accessToken, bookId, cp.chapterId, cp.preRevisionId);
      // This checkpoint (and any NEWER same-chapter ones) are now moot — the
      // draft is back at cp.preRevisionId. Newest-first array ⇒ "newer" = a
      // LOWER index than cp (deterministic, unlike a Date.now() tie-break).
      setCheckpoints((prev) => {
        const idx = prev.findIndex((c) => c.id === cp.id);
        if (idx < 0) return prev;
        return prev.filter((c, i) => c.id !== cp.id && !(c.chapterId === cp.chapterId && i < idx));
      });
    },
    [accessToken, bookId],
  );

  const clear = useCallback(() => setCheckpoints([]), []);

  return { checkpoints, capture, restore, clear };
}

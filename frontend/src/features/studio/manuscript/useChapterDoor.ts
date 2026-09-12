// M3 (newcomer polish F2) — the ONE "start a new chapter" door, shared by every surface a writer
// might reach for it: the Plan Hub "Write a new chapter" button, the Editor's empty state, and the
// manuscript rail's "＋ Chapter". Create a book chapter (unnamed → the display shows "Chapter {n}",
// M1) then open it in the editor, and tell the manuscript navigator to refresh (M2). One home so the
// three doors can never drift (the css-var-duplicated-across-two-consumers-drifts lesson).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useStudioHost } from '../host/StudioHostProvider';

export interface ChapterDoor {
  /** Create a new chapter and open it in the editor. Null ⇒ no auth (render the door disabled). */
  startNewChapter: (() => void) | null;
  creating: boolean;
}

export function useChapterDoor(bookId: string): ChapterDoor {
  const { accessToken } = useAuth();
  const { focusManuscriptUnit, publish, openPanel, getSnapshot } = useStudioHost();
  const qc = useQueryClient();

  // The book's language is required by the create route (never hardcode 'en' — multilingual platform).
  // Cached under the same key PlanHubPanel uses, so this rarely fetches.
  const bookInfo = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken && !!bookId,
  });
  const originalLanguage = bookInfo.data?.original_language ?? 'en';

  const create = useMutation({
    mutationFn: () => booksApi.createChapterEditor(accessToken!, bookId, { original_language: originalLanguage, title: '' }),
    onSuccess: (created) => {
      // Refresh the Plan Hub (react-query) AND the hand-rolled navigator tree (bus, M2).
      //
      // T19 — the PREFIX, not just the simple-chapters list. This narrower key refreshed
      // simple mode only, so a chapter created through this door was invisible on the advanced
      // canvas (keys `arcs` / `overlay` / `scene-links` / the per-node windows) and in the
      // Unplanned tray (`book-chapters`) until a full page reload. A 2026-09-06 run hit exactly
      // that and recorded it as the canvas "not live-updating".
      //
      // Every sibling mutation already invalidates the prefix — usePlanChildCreate,
      // usePlanMoves, usePlanNodeWrites, useExtractPlan. This door was the one that did not, and
      // an invalidation that covers one of five consumers is the shape that makes a widget look
      // broken while the write it reflects succeeded.
      void qc.invalidateQueries({ queryKey: ['plan-hub'] });
      publish({ type: 'manuscriptChanged' });
      if (created?.chapter_id) {
        // F15 (newcomer polish) — don't yank the writer out of an ACTIVE different panel (e.g.
        // the Co-writer Chat) on auto-create. If the editor is already active (or nothing is),
        // focus it as before; otherwise load the chapter into the editor and open it as an
        // INACTIVE tab, so the user stays where they are and switches to it when ready.
        const active = getSnapshot().activePanelIds;
        if (active.length === 0 || active.includes('editor')) {
          focusManuscriptUnit(created.chapter_id);
        } else {
          publish({ type: 'chapter', chapterId: created.chapter_id, bookId });
          openPanel('editor', { focus: false });
        }
      }
    },
  });

  return {
    startNewChapter: accessToken ? () => create.mutate() : null,
    creating: create.isPending,
  };
}

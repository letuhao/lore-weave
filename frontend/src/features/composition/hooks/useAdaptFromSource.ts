// LOOM Composition (M1, D-DERIVATIVE-ADAPT-FROM-SOURCE) — the adaptability GATE for
// the "✦ Adapt from source" action. The action is offered ONLY when ALL hold:
//   1. the open Work is a DERIVATIVE (a canon Work has no source to adapt from),
//   2. the active chapter is AT/AFTER `branch_point` — a pre-divergence chapter is
//      inherited CANON, read-only (the BE `gather_source_scene` also belts this, but
//      we must not OFFER the action there),
//   3. the shared source chapter draft has prose — an empty source must surface a
//      "nothing to adapt" hint, never a silent weak generation (the edge case).
//
// COW shares `book_id` + the chapter spine, so the SOURCE prose is the shared book
// chapter's own draft — the derivative never writes it (the M3 source-clobber guard),
// so `book.get_draft(shared book_id, chapter_id)` IS the inherited source prose.
import { useQuery } from '@tanstack/react-query';
import { booksApi } from '../../books/api';
import type { DerivativeContext } from './useDerivativeContext';

export type Adaptability = {
  /** Offer the adapt action — every gate passes. */
  canAdapt: boolean;
  /** Derivative + at/after branch, but the source chapter has NO prose → show a
   *  "nothing to adapt" hint instead of the action (the BE would otherwise produce a
   *  silent weak generation). */
  sourceEmpty: boolean;
  isLoading: boolean;
};

export function useAdaptFromSource(
  bookId: string,
  chapterId: string,
  derivative: DerivativeContext,
  token: string | null,
): Adaptability {
  const on = derivative.isDerivative && !!token && !!chapterId;

  // The active chapter's reading-order position (the SAME axis `branch_point` lives
  // on). Reused/cached across scenes in the same book.
  const chaptersQ = useQuery({
    queryKey: ['composition', 'adapt-chapters', bookId],
    queryFn: () => booksApi.listChapters(token!, bookId, { lifecycle_state: 'active', limit: 500, offset: 0 }),
    enabled: on,
    select: (d) => d.items,
  });
  const sortOrder = chaptersQ.data?.find((c) => c.chapter_id === chapterId)?.sort_order ?? null;
  const atOrAfterBranch =
    derivative.branchPoint != null && sortOrder != null && sortOrder >= derivative.branchPoint;

  // Only read the source draft once the chapter is known to be at/after the branch —
  // a pre-branch chapter is never adaptable, so don't fetch its prose.
  const draftQ = useQuery({
    queryKey: ['composition', 'adapt-source-draft', bookId, chapterId],
    queryFn: () => booksApi.getDraft(token!, bookId, chapterId),
    enabled: on && atOrAfterBranch,
    retry: false,
  });
  const hasSourceProse = draftQ.isSuccess && !!draftQ.data.text_content?.trim();
  // A 404 / empty draft both mean "no source prose to adapt".
  const draftSettled = draftQ.isSuccess || draftQ.isError;

  return {
    canAdapt: on && atOrAfterBranch && hasSourceProse,
    sourceEmpty: on && atOrAfterBranch && draftSettled && !hasSourceProse,
    isLoading: on && (chaptersQ.isLoading || (atOrAfterBranch && draftQ.isLoading)),
  };
}

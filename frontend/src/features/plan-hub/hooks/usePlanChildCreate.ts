// STRUCTURE ORIGIN (spec 2026-07-17-studio-structure-origin, Bug A) — build the hierarchy DOWN from a
// selected node. Before this, plan-hub could create arcs but a selected arc/chapter dead-ended: the
// drawer had +track/+role (metadata) but no +Chapter/+Scene, so "how do I add items?" had no answer.
//
// Every route here already existed and was verified end-to-end against the live stack (arc → chapter
// → scene all 201/200). This is purely the missing GUI wiring — the repo's engines-gated-on-GUIs gap.
//
// The two verbs are ASYMMETRIC because the model is (checked against the DDL, not guessed):
//   • +Scene  = ONE call: createOutlineNode(kind='scene', chapter_id, parent_id=chapterNodeId).
//   • +Chapter = THREE calls across TWO services, because a chapter's prose is book-service's and its
//     spec placement is composition's, and NodeCreate can't bind the arc on create:
//       1. createBookChapter (book-service)         → the prose unit + its chapter_id
//       2. createOutlineNode(kind='chapter', …)     → the spec node that references it
//       3. assignChapters(arc, [chapterNodeId])     → bind it under the arc (structure_node_id)
//     Steps 2–3 are separate because REST NodeCreate omits structure_node_id (only the repo sets it),
//     so the chapter node is born unassigned and then attached. Verified: assign returns assigned:1.
import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { assignChapters, createBookChapter, createOutlineNode } from '../api';
import type { OutlineNode } from '@/features/composition/types';

export interface PlanChildCreate {
  /** Create a chapter (prose + spec node) under the given arc. Resolves to the chapter outline node,
   *  or null on failure. `projectId` must be a resolved Work; null ⇒ the caller can't offer it. */
  addChapterUnderArc: (arcStructureNodeId: string, title?: string) => Promise<OutlineNode | null>;
  /** Create a scene under a chapter node (which carries the book `chapter_id`). Resolves to the scene
   *  node, or null on failure. */
  addSceneUnderChapter: (chapterNodeId: string, bookChapterId: string, title?: string) => Promise<OutlineNode | null>;
  creating: boolean;
  error: string | null;
  clearError: () => void;
}

export function usePlanChildCreate(
  bookId: string,
  projectId: string | null,
  token: string | null,
  originalLanguage: string,
): PlanChildCreate {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const chapterMutation = useMutation({
    mutationFn: async (v: { arcId: string; title: string }): Promise<OutlineNode> => {
      // 1 — the prose unit (book-service owns chapter creation).
      const { chapter_id } = await createBookChapter(bookId, { title: v.title, original_language: originalLanguage }, token!);
      // 2 — the spec node that references it (unassigned; NodeCreate can't bind the arc).
      const node = await createOutlineNode(projectId!, { kind: 'chapter', chapter_id, title: v.title }, token!);
      // 3 — bind it under the arc. If THIS fails, the chapter + node still exist (unassigned in the
      // pool) — not lost, recoverable by drag/assign — so we surface the error but keep the node.
      await assignChapters(bookId, v.arcId, [node.id], token!);
      return node;
    },
  });

  const sceneMutation = useMutation({
    mutationFn: (v: { chapterNodeId: string; bookChapterId: string; title: string }) =>
      createOutlineNode(projectId!, { kind: 'scene', chapter_id: v.bookChapterId, parent_id: v.chapterNodeId, title: v.title }, token!),
  });

  const settle = useCallback(() => void qc.invalidateQueries({ queryKey: ['plan-hub'] }), [qc]);

  const addChapterUnderArc = useCallback(
    async (arcStructureNodeId: string, title = 'Untitled chapter'): Promise<OutlineNode | null> => {
      setError(null);
      if (!projectId || !token) { setError('This book has no co-writer set up yet.'); return null; }
      try {
        const node = await chapterMutation.mutateAsync({ arcId: arcStructureNodeId, title });
        settle();
        return node;
      } catch (e) {
        setError((e as Error)?.message || 'Could not add the chapter.');
        settle(); // a partial (chapter made, assign failed) still needs the canvas to refetch
        return null;
      }
    },
    [chapterMutation, projectId, token, settle],
  );

  const addSceneUnderChapter = useCallback(
    async (chapterNodeId: string, bookChapterId: string, title = 'Untitled scene'): Promise<OutlineNode | null> => {
      setError(null);
      if (!projectId || !token) { setError('This book has no co-writer set up yet.'); return null; }
      try {
        const node = await sceneMutation.mutateAsync({ chapterNodeId, bookChapterId, title });
        settle();
        return node;
      } catch (e) {
        setError((e as Error)?.message || 'Could not add the scene.');
        return null;
      }
    },
    [sceneMutation, projectId, token, settle],
  );

  return {
    addChapterUnderArc,
    addSceneUnderChapter,
    creating: chapterMutation.isPending || sceneMutation.isPending,
    error,
    clearError: useCallback(() => setError(null), []),
  };
}

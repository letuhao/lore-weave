// STRUCTURE ORIGIN (spec docs/specs/2026-07-17-studio-structure-origin.md §3.2) — the one verb that
// works on an EMPTY book, and the exit from the Studio's zero-state dead loop.
//
// THE BUG THIS EXISTS FOR (docs/bugs/2026-07-17-studio-first-use-cold-start.md): a first-time user
// faced four doors and all four were locked — the Manuscript `+` was never wired, the Editor pointed
// back at it, plan-hub's "Extract" needs parsed scenes a new book has none of, and "Plan from
// scratch" is not from scratch (PlannerPanel.tsx:120 hard-gates Propose on a pre-written braindump).
// Nothing in the Studio created the first thing.
//
// WHY THIS COMPOSES RATHER THAN IMPLEMENTS: the Work + knowledge-project bootstrap is already solved,
// idempotent, race-safe and outage-resilient — `POST /books/{id}/work` (works.py:163) resolves-or-
// creates the KG project then get-or-creates the row, and `useCreateWork` / `usePendingWorkResolver`
// already drive its C16 pending→backfill path. That work was done once, mounted ONLY on the Quality
// panels (WorkSetupCta), and was therefore invisible everywhere a writer starts. We mount the HOOKS
// rather than re-solve it — re-solving it a third time is how this bug class keeps shipping.
//
// ORDERING IS LOAD-BEARING:
//   1. createArc FIRST. An arc is a `structure_node`, keyed by book_id — NOT project_id
//      (migrate.py:1157-1165) — so it needs NO Work and cannot be blocked by knowledge being down.
//      It is the visible act: the writer asked for structure and must get structure.
//   2. ensure Work SECOND, best-effort. Outline nodes (chapters/scenes) DO need project_id, so the
//      Work must exist before the next step — but it must never gate step 1. If knowledge is down the
//      Work lands pending (project_id null) and the resolver polls the backfill; the arc is already
//      on the canvas either way.
// Inverting these would re-introduce the outage as a wall in front of the origin, which is exactly
// what C16 was built to prevent.
import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCreateWork, usePendingWorkResolver } from '@/features/composition/hooks/useWork';
import { createArc } from '../api';
import type { ArcListNode } from '../types';

export interface PlanOrigin {
  /** Create an arc (and ensure the book's Work). At the empty state this is the ORIGIN — the book's
   *  first arc. On a populated canvas it is also the "+ Arc" / "+ Sub-arc" verb: same route, same
   *  idempotent Work-ensure (a no-op once the Work exists). `parentArcId` nests it as a sub-arc.
   *  Resolves to the created arc (so the caller can select it for inline rename), or null on failure. */
  start: (title: string, parentArcId?: string) => Promise<ArcListNode | null>;
  creating: boolean;
  error: string | null;
  clearError: () => void;
}

export function usePlanOrigin(bookId: string, token: string | null): PlanOrigin {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const createWork = useCreateWork(bookId, token);
  const resolver = usePendingWorkResolver(bookId, token);

  const arcMutation = useMutation({
    mutationFn: (v: { title: string; parentArcId?: string }) =>
      createArc(bookId, { kind: 'arc', title: v.title, parent_arc_id: v.parentArcId ?? null }, token!),
  });

  const start = useCallback(
    async (title: string, parentArcId?: string): Promise<ArcListNode | null> => {
      setError(null);
      let arc: ArcListNode;
      try {
        // 1 — the visible act. Book-scoped: no Work required, so a knowledge outage cannot block it.
        arc = await arcMutation.mutateAsync({ title, parentArcId });
      } catch (e) {
        const err = e as Error;
        setError(err?.message || 'Could not create the arc.');
        return null;
      }

      // 2 — housekeeping, best-effort. The arc already exists; a Work failure must NOT read as
      // "your arc wasn't created", so this never throws out of `start` and never clears `arc`.
      try {
        const work = await createWork.mutateAsync();
        // Greenfield Work created during a knowledge outage → project_id null. Poll the backfill by
        // its surrogate id (the resolve query excludes pending works, so a refetch can't find it).
        if (!work.project_id && work.id) resolver.start(work.id);
      } catch {
        // Swallowed ON PURPOSE, and only here: the user's arc IS on the canvas. Surfacing a Work
        // error next to a successful arc would be a lie about what happened. The Work is idempotent,
        // so the next surface that needs it (any outline write) re-runs this and reports honestly.
      }

      void qc.invalidateQueries({ queryKey: ['plan-hub'] });
      return arc;
    },
    [arcMutation, createWork, resolver, qc],
  );

  return {
    start,
    creating: arcMutation.isPending,
    error,
    clearError: useCallback(() => setError(null), []),
  };
}

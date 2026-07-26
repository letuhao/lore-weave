// W10 §12.5 — the apply-PREVIEW controller. "Write a new arc from this template" =
// decompose at arc scale: pick a target chapter count + bind the arc_roster once, then
// POST …/apply → the deterministic plan (rescaled placements + drop/merge report). The
// call is PURE (the server persists nothing); we render the plan for review. The deep
// materialization into committed outline_node rows is the tracked follow-up
// (D-W10-APPLY-PLANNER-MATERIALIZE) — this surface is preview-only by design. No JSX.
import { useCallback, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { arcApi } from '../arcApi';
import type { ArcApplyPlan } from '../arcTypes';

export function useArcApplyPreview(arcId: string | null, token: string | null, defaultTarget: number) {
  const [targetChapters, setTargetChapters] = useState<number>(Math.max(1, defaultTarget));
  const [rosterBindings, setRosterBindings] = useState<Record<string, string>>({});

  const preview = useMutation<ArcApplyPlan, Error>({
    mutationFn: () => {
      // drop empty bindings so the server only sees real role bindings.
      const bound: Record<string, string> = {};
      for (const [k, v] of Object.entries(rosterBindings)) {
        if (v.trim()) bound[k] = v.trim();
      }
      return arcApi.apply(arcId!, { target_chapters: targetChapters, roster_bindings: bound }, token!);
    },
  });

  const setBinding = useCallback((key: string, value: string) => {
    setRosterBindings((prev) => ({ ...prev, [key]: value }));
  }, []);

  const run = useCallback(() => {
    if (arcId && token) preview.mutate();
  }, [arcId, token, preview]);

  return {
    targetChapters,
    setTargetChapters: (n: number) => setTargetChapters(Math.max(1, Math.floor(n) || 1)),
    rosterBindings,
    setBinding,
    run,
    plan: preview.data,
    isPending: preview.isPending,
    isError: preview.isError,
  };
}

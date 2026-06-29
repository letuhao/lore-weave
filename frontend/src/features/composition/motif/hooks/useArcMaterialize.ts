// W10 — the MATERIALIZE controller (D-W10-APPLY-PLANNER-MATERIALIZE). Commits an arc
// template onto a work's book (a real arc→chapter→scene outline + motif_application
// ledger) via POST …/works/{projectId}/arc/materialize. A 409 (a chapter already has a
// plan) is surfaced as `conflict` so the UI can offer a replace. On success it
// invalidates the planner's decompose preview so the committed tree shows up. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { arcApi } from '../arcApi';
import type { ArcMaterializeArgs, ArcMaterializeResult } from '../arcTypes';

export function useArcMaterialize(projectId: string | null, token: string | null) {
  const qc = useQueryClient();
  const mut = useMutation<ArcMaterializeResult, Error & { status?: number }, ArcMaterializeArgs>({
    mutationFn: (args) => arcApi.materialize(projectId!, args, token!),
    onSuccess: () => {
      // the committed outline changes the planner tree + the per-scene bindings.
      qc.invalidateQueries({ queryKey: ['composition', 'decompose', projectId] });
      qc.invalidateQueries({ queryKey: ['composition', 'motif-bindings', projectId] });
    },
  });
  return {
    run: (args: ArcMaterializeArgs) => mut.mutate(args),
    result: mut.data,
    isPending: mut.isPending,
    isError: mut.isError,
    // 409 CHAPTER_ALREADY_PLANNED — the UI offers "Replace existing".
    conflict: (mut.error as { status?: number } | null)?.status === 409,
    reset: mut.reset,
  };
}

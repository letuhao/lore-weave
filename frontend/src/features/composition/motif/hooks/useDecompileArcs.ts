// S-10 O6c — the "Group my chapters into arcs" controller. Runs the deterministic arc decompiler via
// POST /books/{bookId}/arcs/decompile (EDIT). Idempotent — re-running reuses existing decompiled arcs
// by position, so a double-click is safe. On success it invalidates the plan-hub arc shell so the new
// arc layer appears. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { arcApi, type ArcDecompileResult } from '../arcApi';

export function useDecompileArcs(bookId: string | null, token: string | null) {
  const qc = useQueryClient();
  const mut = useMutation<ArcDecompileResult, Error, number>({
    mutationFn: (chaptersPerArc) => arcApi.decompile(bookId!, chaptersPerArc, token!),
    onSuccess: () => {
      // the new arc layer changes the plan-hub shell + the arc list.
      qc.invalidateQueries({ queryKey: ['plan-hub', 'arcs', bookId] });
      qc.invalidateQueries({ queryKey: ['plan-hub'] });
    },
  });
  return {
    run: (chaptersPerArc: number) => mut.mutate(chaptersPerArc),
    result: mut.data,
    isPending: mut.isPending,
    isError: mut.isError,
    reset: mut.reset,
  };
}

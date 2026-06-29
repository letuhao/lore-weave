// WI-4 (D-MOTIF-SYNC-3WAY-BASE) — the upstream-sync controller for an adopted motif.
// Fetches the per-field diff vs the current upstream (only for source='adopted' rows) and
// applies the chosen merge (accept = the upstream fields to take; [] = keep all local +
// re-pin). The diff query never retries — 409 (not-adopted) / 410 (upstream gone) are
// expected terminal states, not transient. No JSX — SyncDiffDrawer renders.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motifApi } from '../api';
import type { Motif } from '../types';

export function useMotifSync(motif: Motif | null, token: string | null) {
  const qc = useQueryClient();
  const isAdopted = !!motif && motif.source === 'adopted';

  const diffQ = useQuery({
    queryKey: ['composition', 'motif-sync', motif?.id],
    queryFn: () => motifApi.upstreamDiff(motif!.id, token!),
    enabled: !!token && isAdopted,
    retry: false,             // 409/410 are terminal (not-adopted / upstream gone)
    staleTime: 60_000,
  });

  const apply = useMutation({
    mutationFn: (accept: string[]) => motifApi.sync(motif!.id, accept, token!),
    onSuccess: () => {
      // the merged motif + its detail + this diff all changed → refresh.
      qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
      qc.invalidateQueries({ queryKey: ['composition', 'motif', motif?.id] });
      qc.invalidateQueries({ queryKey: ['composition', 'motif-sync', motif?.id] });
    },
  });

  return {
    isAdopted,
    diff: diffQ.data ?? null,
    hasUpdate: diffQ.data?.update_available ?? false,
    isLoading: diffQ.isLoading,
    isError: diffQ.isError,        // e.g. 410 upstream gone — no banner
    apply,
  };
}

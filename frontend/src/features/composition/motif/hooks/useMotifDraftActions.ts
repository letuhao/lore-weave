// WI-1 — the mining-review actions: promote a mined draft into the active library
// (status draft → active, the owner-only PATCH) or discard it (soft archive). Both
// invalidate the motif lists so the Drafts tab + the active library refresh. No JSX.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { motifApi } from '../api';

export function useMotifDraftActions(token: string | null) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });

  const promote = useMutation({
    mutationFn: (m: { id: string; version: number }) => motifApi.promote(m.id, m.version, token!),
    onSuccess: invalidate,
  });
  const discard = useMutation({
    mutationFn: (id: string) => motifApi.archive(id, token!),
    onSuccess: invalidate,
  });
  // S-08 — un-archive back into the active library (the reverse of discard/archive). Invalidates the
  // motif lists so the row leaves the Archived scope and reappears under My library.
  const restore = useMutation({
    mutationFn: (id: string) => motifApi.restore(id, token!),
    onSuccess: invalidate,
  });

  return { promote, discard, restore };
}

// W6 §3.2 — one motif + clone/patch/archive mutations. Derives isReadOnly so the
// view disables edits + shows "clone to edit" (the kinds-bug lesson: a user never
// edits a shared row). No JSX.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motifApi } from '../api';
import { isReadOnly } from '../simpleMode';
import type { Motif, MotifPatchArgs } from '../types';

export function useMotifDetail(motifId: string | null, meUserId: string | null, token: string | null) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['composition', 'motifs'] });
    if (motifId) qc.invalidateQueries({ queryKey: ['composition', 'motif', motifId] });
  };

  const query = useQuery({
    queryKey: ['composition', 'motif', motifId],
    queryFn: () => motifApi.get(motifId!, token!),
    enabled: !!motifId && !!token,
  });

  const motif = query.data ?? null;
  const readOnly = motif ? isReadOnly(motif, meUserId) : false;

  const patch = useMutation({
    mutationFn: (v: { args: MotifPatchArgs; version: number }) =>
      motifApi.patch(motifId!, v.args, v.version, token!),
    onSuccess: invalidate,
  });

  const archive = useMutation({
    mutationFn: () => motifApi.archive(motifId!, token!),
    onSuccess: invalidate,
  });

  return {
    motif: motif as Motif | null,
    isLoading: query.isLoading,
    isError: query.isError,
    readOnly,
    patch,
    archive,
    refetch: query.refetch,
  };
}

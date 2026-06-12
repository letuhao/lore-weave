// LOOM Composition (M8) — canon-rules CRUD controller (react-query).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { CanonRule } from '../types';

export function useCanonRules(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  const key = ['composition', 'canon', projectId];
  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const list = useQuery({
    queryKey: key,
    queryFn: () => compositionApi.listCanonRules(projectId!, token!),
    enabled: !!projectId && !!token,
    select: (d): CanonRule[] => d.rules,
  });

  const create = useMutation({
    mutationFn: (payload: Partial<CanonRule>) => compositionApi.createCanonRule(projectId!, payload, token!),
    onSuccess: invalidate,
  });
  const patch = useMutation({
    mutationFn: (v: { id: string; payload: Partial<CanonRule>; version: number }) =>
      compositionApi.patchCanonRule(v.id, v.payload, v.version, token!),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (id: string) => compositionApi.deleteCanonRule(id, token!),
    onSuccess: invalidate,
  });

  return { list, create, patch, remove };
}

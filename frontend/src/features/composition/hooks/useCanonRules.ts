// LOOM Composition (M8) — canon-rules CRUD controller (react-query).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { CanonRule } from '../types';

export function useCanonRules(
  projectId: string | undefined, token: string | null,
  opts?: { includeArchived?: boolean },
) {
  const qc = useQueryClient();
  const includeArchived = opts?.includeArchived ?? false;
  // The list key carries includeArchived (the archived + non-archived lists are distinct caches),
  // but invalidate uses the BASE prefix so a write refreshes BOTH variants — and so the Lane-B
  // agent-parity handler (which invalidates ['composition','canon',projectId]) still prefix-matches.
  const baseKey = ['composition', 'canon', projectId];
  const invalidate = () => qc.invalidateQueries({ queryKey: baseKey });

  const list = useQuery({
    queryKey: [...baseKey, { includeArchived }],
    queryFn: () => compositionApi.listCanonRules(projectId!, token!, { includeArchived }),
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
  const restore = useMutation({
    mutationFn: (id: string) => compositionApi.restoreCanonRule(id, token!),
    onSuccess: invalidate,
  });

  return { list, create, patch, remove, restore };
}

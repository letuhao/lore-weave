// LOOM Composition (T1.1a) — committed-outline read controller (react-query).
// Read-only for slice a (the navigable Act→Chapter→Scene browser); node CRUD +
// reorder + cards mode land in T1.1b/c/d. Mirrors useCanonRules.
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { OutlineNode } from '../types';

export function useOutline(projectId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: ['composition', 'outline', projectId],
    queryFn: () => compositionApi.getOutline(projectId!, token!),
    enabled: !!projectId && !!token,
    select: (d): OutlineNode[] => d.nodes,
  });
}

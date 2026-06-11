// LOOM Composition (T0.1) — narrative-thread debt read controller (react-query).
// Mirrors useCanonRules: a read-only query over the promise ledger. The panel is
// advisory (D4) — there are no mutations (the ledger is written by the generation
// flow, not here).
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../api';

export function useNarrativeThreads(
  projectId: string | undefined,
  token: string | null,
  status: 'open' | 'all',
) {
  return useQuery({
    queryKey: ['composition', 'threads', projectId, status],
    queryFn: () => compositionApi.listNarrativeThreads(projectId!, status, token!),
    enabled: !!projectId && !!token,
  });
}

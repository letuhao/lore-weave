// D-W10-ARC-CONFORMANCE-FE — read the coarse arc-conformance report (the structural
// diff of the materialized bindings vs the arc template). Gated on a projectId (a work
// must exist for there to be realized bindings) + the arc id + token. No JSX.
import { useQuery } from '@tanstack/react-query';
import { motifApi } from '../api';
import type { ArcConformance } from '../types';

export function useArcConformance(
  projectId: string | null | undefined,
  arcTemplateId: string | null | undefined,
  token: string | null,
) {
  return useQuery<ArcConformance>({
    queryKey: ['composition', 'arc-conformance', projectId, arcTemplateId],
    queryFn: () => motifApi.arcConformance(projectId!, arcTemplateId!, token!),
    enabled: !!projectId && !!arcTemplateId && !!token,
    staleTime: 30_000,
  });
}

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
  // deep=true adds the realized-from-PROSE overlay (a cross-service read) — off by default
  // so opening an arc does the cheap coarse diff; the user opts in (a button).
  deep = false,
  // modelRef opts deep into THREAD-TAGGING (tags the book's events → deep thread-progression);
  // null ⇒ pacing + any pre-existing tags only.
  modelRef?: string | null,
) {
  return useQuery<ArcConformance>({
    queryKey: ['composition', 'arc-conformance', projectId, arcTemplateId, deep, modelRef ?? null],
    queryFn: () => motifApi.arcConformance(projectId!, arcTemplateId!, token!, deep, modelRef),
    enabled: !!projectId && !!arcTemplateId && !!token,
    staleTime: 30_000,
  });
}

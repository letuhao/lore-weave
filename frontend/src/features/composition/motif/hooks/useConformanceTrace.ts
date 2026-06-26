// W6 §3.2 — chapter-scope conformance read + regenerate-to-beat + the Tier-W
// re-run flow. Surfaces `calibrated` so the view stamps "advisory / unverified"
// (R2.1 — AI honesty). The re-run is a confirm-token spend (mint→confirm→poll); the
// FE never executes it. No JSX.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { motifApi } from '../api';
import type { ChapterConformance, CostEstimate } from '../types';

export function useConformanceTrace(
  projectId: string | undefined, chapterId: string | undefined, token: string | null,
) {
  const qc = useQueryClient();
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const key = ['composition', 'conformance', projectId, chapterId];
  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const query = useQuery({
    queryKey: key,
    queryFn: () => motifApi.conformance(projectId!, chapterId!, token!),
    enabled: !!projectId && !!chapterId && !!token,
    select: (d): ChapterConformance => d,
  });

  const regenerateToBeat = useMutation({
    mutationFn: (nodeId: string) => motifApi.regenerateToBeat(projectId!, nodeId, token!),
    onSuccess: invalidate,
  });

  // Tier-W re-run: mint → confirm → poll → refresh.
  const mintRun = useMutation({
    mutationFn: () => motifApi.conformanceRunEstimate(projectId!, chapterId!, token!),
    onSuccess: (est) => setEstimate(est),
  });
  const confirmRun = useMutation({
    mutationFn: () => motifApi.conformanceRunConfirm(estimate!.confirm_token, token!),
    onSuccess: () => { setEstimate(null); invalidate(); },
  });
  const cancelRun = () => setEstimate(null);

  return {
    conformance: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
    regenerateToBeat,
    estimate,
    mintRun,
    confirmRun,
    cancelRun,
  };
}

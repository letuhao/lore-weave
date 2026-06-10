// LOOM Composition (V1 slice 5) — eval-gate dashboard controller.
//
// Reads the per-Work, per-mode correction rates (the V1 quality signal that
// replaces the saturating auto-judge). Cold-start safe: rates come back null
// until real generations accumulate.
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../api';

export function useCorrectionStats(projectId: string | null, token: string | null) {
  return useQuery({
    queryKey: ['composition', 'correction-stats', projectId],
    queryFn: () => compositionApi.getCorrectionStats(projectId!, token!),
    enabled: !!projectId && !!token,
  });
}

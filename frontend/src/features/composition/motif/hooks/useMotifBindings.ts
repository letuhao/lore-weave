// D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — fetch the POST-commit per-scene motif
// bindings for a committed chapter ({ node_id: SceneBoundMotif | null }). The planner
// renders MotifBindingCard per committed scene from this map. Query is gated on a
// chapterId (disabled until a chapter is committed) + the token. No JSX.
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../../api';
import type { MotifBindingsResponse } from '../types';

export function useMotifBindings(projectId: string, chapterId: string | null, token: string | null) {
  return useQuery<MotifBindingsResponse>({
    queryKey: ['composition', 'motif-bindings', projectId, chapterId],
    queryFn: () => compositionApi.getMotifBindings(projectId, chapterId!, token!),
    enabled: !!projectId && !!chapterId && !!token,
    staleTime: 30_000,
  });
}

// LOOM Composition (T4.1) — the canon-growth flywheel.
import { useQuery } from '@tanstack/react-query';
import { knowledgeApi, type FlywheelDeltaWire } from '@/features/knowledge/api';

/**
 * The net-new entities/relations/events added by the latest COMPLETED extraction
 * job for this project — the "+N added" the Flywheel panel celebrates after a
 * publish→extraction. The composition `projectId` IS the knowledge project id.
 * `has_delta=false` (no extraction yet) is a valid, non-error empty state.
 */
export function useFlywheel(projectId: string | undefined, token: string | null) {
  return useQuery<FlywheelDeltaWire>({
    queryKey: ['composition', 'flywheel', projectId],
    queryFn: () => knowledgeApi.getFlywheel(projectId!, token!),
    enabled: !!projectId && !!token,
  });
}

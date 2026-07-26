// Part B — the ONE readiness signal the onboarding door consumes to decide whether to offer the
// "Set up this book" shortcut (create BOTH prerequisites at once), so a work-gated surface can also
// light up the plan-gated ones instead of leaving the book half-set-up.
//
// Two prerequisites (they remain distinct even post-C-merge: structure vs the knowledge Work):
//   • hasWork — a composition Work with a resolved knowledge project_id.
//   • hasPlan — at least one arc/structure_node (kind='saga'|'arc' — the plan; parts don't count).
//
// Both reads REUSE the queries their surfaces already run (Work resolution + the shared
// ['plan-hub','arcs',bookId] arcs query), so mounting this adds NO network call — react-query dedupes.
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { getArcs } from '@/features/plan-hub/api';

export interface BookReadiness {
  hasWork: boolean;
  hasPlan: boolean;
  loading: boolean;
}

export function useBookReadiness(bookId: string): BookReadiness {
  const { accessToken } = useAuth();

  const resolution = useWorkResolution(bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(bookId, accessToken);
  const work = resolveActiveWork(resolution.data, activeWorkId);

  const arcs = useQuery({
    queryKey: ['plan-hub', 'arcs', bookId], // shared key ⇒ no extra fetch (PH25)
    queryFn: () => getArcs(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
  });

  return {
    hasWork: !!work?.project_id,
    hasPlan: (arcs.data?.arcs?.length ?? 0) > 0,
    loading: resolution.isLoading || arcs.isLoading,
  };
}

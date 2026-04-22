import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type EntityDetail } from '../api';

// K19d.4 — detail hook for the slide-over panel. Enabled ONLY when a
// concrete entityId is supplied so the tab's default (no row
// selected) state doesn't burn a query. staleTime 10s because
// relations change slowly (only on extraction, merge, or delete).
//
// queryKey prefixes userId to prevent cross-tenant cache leak on
// shared QueryClient logout→login swap (review-impl M1, matches
// K19c.4 useUserEntities precedent). Entity IDs are hash-based so
// cross-user collision is vanishingly unlikely, but the pattern
// stays consistent with useEntities so future audits see one rule.

export interface UseEntityDetailResult {
  detail: EntityDetail | null;
  isLoading: boolean;
  error: Error | null;
}

export function useEntityDetail(
  entityId: string | null,
): UseEntityDetailResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['knowledge-entity-detail', userId, entityId] as const,
    queryFn: () => knowledgeApi.getEntityDetail(entityId!, accessToken!),
    enabled: !!accessToken && !!entityId,
    staleTime: 10_000,
  });

  return {
    detail: query.data ?? null,
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
  };
}

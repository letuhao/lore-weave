import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type EntitiesBrowseResponse,
  type EntitiesListParams,
} from '../api';

// K19d.2 — browse hook for the Entities tab. queryKey scoping is by
// full params object PLUS userId — react-query shallow-compares array
// contents, so changing any filter correctly triggers a refetch. The
// userId prefix prevents a logout→login swap on a shared QueryClient
// from handing back the previous user's cached entities during the
// 30s staleTime window (review-impl M1, matches K19c.4
// useUserEntities precedent). staleTime is short (30s) because the
// tab is for active curation work; users expect fresh data after
// they merge/edit (which γ will ship).

export interface UseEntitiesResult {
  entities: EntitiesBrowseResponse['entities'];
  total: number;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
}

export function useEntities(params: EntitiesListParams): UseEntitiesResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: [
      'knowledge-entities',
      userId,
      params.project_id ?? null,
      params.kind ?? null,
      params.search ?? null,
      params.limit ?? 50,
      params.offset ?? 0,
    ] as const,
    queryFn: () => knowledgeApi.listEntities(params, accessToken!),
    enabled: !!accessToken,
    staleTime: 30_000,
  });

  return {
    entities: query.data?.entities ?? [],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
  };
}

import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type DrawerSearchParams,
  type DrawerSearchResponse,
} from '../api';

// K19e.5 — drawer semantic-search hook for the Raw tab. queryKey is
// userId-prefixed (K19d β M1: cross-tenant flash guard on shared
// QueryClient logout→login). Disabled whenever projectId is empty OR
// query is shorter than MIN_QUERY_LENGTH so typing two letters into
// the search box doesn't burn a provider-registry embed call + a
// Neo4j vector search per keystroke.
//
// ``retry: false`` because drawer errors are either user config
// (wrong model) or transient provider blips — silent auto-retry
// wastes BYOK quota. The Raw tab surfaces a manual Retry button when
// the BE says ``retryable=true``.

export const DRAWER_SEARCH_MIN_QUERY_LENGTH = 3;

export interface UseDrawerSearchResult {
  hits: DrawerSearchResponse['hits'];
  embeddingModel: string | null;
  /** True when the hook is actively disabled because the user hasn't
   *  supplied a project + meaningful query yet. The tab uses this to
   *  render a "pick a project / type a query" prompt instead of an
   *  empty-results state. */
  disabled: boolean;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
}

export function useDrawerSearch(
  params: DrawerSearchParams,
): UseDrawerSearchResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const queryActive =
    !!params.project_id &&
    params.query.length >= DRAWER_SEARCH_MIN_QUERY_LENGTH;

  const query = useQuery({
    queryKey: [
      'knowledge-drawers',
      userId,
      params.project_id,
      params.query,
      params.limit ?? 40,
    ] as const,
    queryFn: () => knowledgeApi.searchDrawers(params, accessToken!),
    enabled: !!accessToken && queryActive,
    retry: false,
    staleTime: 30_000,
  });

  return {
    hits: query.data?.hits ?? [],
    embeddingModel: query.data?.embedding_model ?? null,
    disabled: !queryActive,
    // react-query already keeps isLoading=false when enabled=false, so
    // no additional queryActive guard is needed here.
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: (query.error as Error | null) ?? null,
  };
}

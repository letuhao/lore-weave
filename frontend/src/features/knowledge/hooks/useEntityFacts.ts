import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type EntityFact } from '../api';

// C9 (C9-promote-flow) — known-facts hook for the entity-detail panel.
//
// Powers the provenance MVP: the facts list ABOUT an entity (decision /
// preference / milestone / negation) + each fact's `source_chapter`. Full
// passage-trail provenance is deferred (LOCKED).
//
// Enabled ONLY when a concrete entityId is supplied so the tab's default
// (no row selected) doesn't burn a query. No spoiler window passed — the
// curation view is author-facing (whole-book), not a reader codex.
//
// queryKey prefixes userId to prevent cross-tenant cache leak on a shared
// QueryClient logout→login swap (matches useEntityDetail / useUserEntities).

export interface UseEntityFactsResult {
  facts: EntityFact[];
  windowAvailable: boolean;
  isLoading: boolean;
  error: Error | null;
}

export function useEntityFacts(
  entityId: string | null,
): UseEntityFactsResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['knowledge-entity-facts', userId, entityId] as const,
    queryFn: () => knowledgeApi.getEntityFacts(entityId!, {}, accessToken!),
    enabled: !!accessToken && !!entityId,
    staleTime: 10_000,
  });

  return {
    facts: query.data?.facts ?? [],
    windowAvailable: query.data?.window_available ?? false,
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
  };
}

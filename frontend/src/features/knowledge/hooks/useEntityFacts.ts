import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type CreateEntityFactPayload, type EntityFact } from '../api';

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
    // S-05 — curation=true: the author-facing whole-book read (no spoiler window).
    // Without it the server fails closed (before_order=-1) and the list is ALWAYS
    // empty in the studio — the pre-existing empty-shell bug this fixes.
    queryFn: () =>
      knowledgeApi.getEntityFacts(entityId!, { curation: true }, accessToken!),
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

// ── S-05 — author + invalidate mutations (co-located so they share the facts
//    query key + invalidate it on success). ────────────────────────────────

/** Author a fact ABOUT an entity → refetch that entity's facts so it appears. */
export function useCreateEntityFact(
  entityId: string | null,
  options?: { onSuccess?: () => void; onError?: (e: Error) => void },
) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (payload: CreateEntityFactPayload) =>
      knowledgeApi.createEntityFact(entityId!, payload, accessToken!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-facts', userId, entityId],
      });
      options?.onSuccess?.();
    },
    onError: (e) => options?.onError?.(e as Error),
  });
  return { create: mutation.mutateAsync, isPending: mutation.isPending };
}

/** Mark a committed fact wrong → invalidate → refetch so it drops from the list. */
export function useInvalidateFact(
  entityId: string | null,
  options?: { onSuccess?: () => void; onError?: (e: Error) => void },
) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (factId: string) =>
      knowledgeApi.invalidateFact(factId, accessToken!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-facts', userId, entityId],
      });
      options?.onSuccess?.();
    },
    onError: (e) => options?.onError?.(e as Error),
  });
  return { invalidate: mutation.mutateAsync, isPending: mutation.isPending };
}

/** S-05b — UNDO a mark-wrong: revalidate → refetch so the fact re-appears. */
export function useRevalidateFact(
  entityId: string | null,
  options?: { onSuccess?: () => void; onError?: (e: Error) => void },
) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (factId: string) =>
      knowledgeApi.revalidateFact(factId, accessToken!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-facts', userId, entityId],
      });
      options?.onSuccess?.();
    },
    onError: (e) => options?.onError?.(e as Error),
  });
  return { revalidate: mutation.mutateAsync, isPending: mutation.isPending };
}

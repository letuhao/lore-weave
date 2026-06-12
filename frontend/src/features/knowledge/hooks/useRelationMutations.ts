import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type EntityRelation,
  type RelationCorrectPayload,
} from '../api';

// Phase B C-FE — relation correction mutation hooks.
//
// Relations render inside the entity detail panel of BOTH endpoints, so both
// invalidate the ['knowledge-entity-detail', userId] prefix — refreshing any
// open detail (subject's or object's) so the corrected/invalidated edge
// reflects without a manual reload. Prefix-match covers whichever endpoint the
// user has open.

function useDetailInvalidation() {
  const { user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({
      queryKey: ['knowledge-entity-detail', userId],
    });
  };
}

export interface UseInvalidateRelationResult {
  invalidate: (args: { relationId: string }) => Promise<EntityRelation>;
  isPending: boolean;
  error: Error | null;
}

/** Mark a relation wrong → soft-invalidate (spurious-drop correction). */
export function useInvalidateRelation(options?: {
  onSuccess?: (rel: EntityRelation) => void;
  onError?: (err: Error) => void;
}): UseInvalidateRelationResult {
  const { accessToken } = useAuth();
  const invalidateDetail = useDetailInvalidation();

  const mutation = useMutation({
    mutationFn: async (args: { relationId: string }) =>
      knowledgeApi.invalidateRelation(args.relationId, accessToken!),
    onSuccess: async (rel) => {
      await invalidateDetail();
      options?.onSuccess?.(rel);
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  return {
    invalidate: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

export interface UseCorrectRelationResult {
  correct: (args: { payload: RelationCorrectPayload }) => Promise<EntityRelation>;
  isPending: boolean;
  error: Error | null;
}

/** Fix a relation: invalidate old + recreate corrected (predicate-fix). */
export function useCorrectRelation(options?: {
  onSuccess?: (rel: EntityRelation) => void;
  onError?: (err: Error) => void;
}): UseCorrectRelationResult {
  const { accessToken } = useAuth();
  const invalidateDetail = useDetailInvalidation();

  const mutation = useMutation({
    mutationFn: async (args: { payload: RelationCorrectPayload }) =>
      knowledgeApi.correctRelation(args.payload, accessToken!),
    onSuccess: async (rel) => {
      await invalidateDetail();
      options?.onSuccess?.(rel);
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  return {
    correct: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

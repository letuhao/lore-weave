import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type Entity,
  type EntityMergeErrorCode,
  type EntityMergeResponse,
  type EntityUpdatePayload,
} from '../api';

// K19d γ-a + γ-b — mutation hooks for the Entity detail panel.
//
// Invalidation strategy: both edit and merge trigger a refetch of:
//   - ['knowledge-entities', userId, ...] — the browse list
//   - ['knowledge-entity-detail', userId, entityId] — the open detail
// so the table row (renamed/merged) and the open panel reflect the
// new state without a manual reload. Prefix-match invalidation
// (only user scope specified) covers every filter/pagination
// permutation the user may have open in the list.

export interface UseUpdateEntityResult {
  update: (args: { entityId: string; payload: EntityUpdatePayload }) => Promise<Entity>;
  isPending: boolean;
  error: Error | null;
}

export function useUpdateEntity(options?: {
  onSuccess?: (entity: Entity) => void;
  onError?: (err: Error) => void;
}): UseUpdateEntityResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: { entityId: string; payload: EntityUpdatePayload }) => {
      return knowledgeApi.updateEntity(args.entityId, args.payload, accessToken!);
    },
    onSuccess: async (entity) => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entities', userId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-detail', userId, entity.id],
      });
      options?.onSuccess?.(entity);
    },
    onError: (err) => {
      options?.onError?.(err as Error);
    },
  });

  return {
    update: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

// ── γ-b merge ────────────────────────────────────────────────────────

export interface MergeEntityError extends Error {
  status?: number;
  errorCode: EntityMergeErrorCode;
  detailMessage?: string;
}

function parseMergeError(err: unknown): MergeEntityError {
  const e = err as {
    message?: string;
    status?: number;
    body?: { detail?: { error_code?: string; message?: string } };
  };
  const detail = e.body?.detail;
  const code = (detail?.error_code ?? 'unknown') as EntityMergeErrorCode;
  return Object.assign(new Error(e.message || 'merge failed'), {
    status: e.status,
    errorCode: code,
    detailMessage: detail?.message,
  });
}

export interface UseMergeEntityResult {
  merge: (args: {
    sourceId: string;
    targetId: string;
  }) => Promise<EntityMergeResponse>;
  isPending: boolean;
  error: MergeEntityError | null;
}

export function useMergeEntity(options?: {
  onSuccess?: (resp: EntityMergeResponse) => void;
  onError?: (err: MergeEntityError) => void;
}): UseMergeEntityResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation<
    EntityMergeResponse,
    MergeEntityError,
    { sourceId: string; targetId: string }
  >({
    mutationFn: async ({ sourceId, targetId }) => {
      try {
        return await knowledgeApi.mergeEntityInto(sourceId, targetId, accessToken!);
      } catch (err) {
        throw parseMergeError(err);
      }
    },
    onSuccess: async (resp, variables) => {
      // Source is gone; target absorbed its content. Invalidate
      // both so list + any open detail reflect reality. Also
      // evict the source's detail cache — the next detail fetch
      // on that id would 404.
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entities', userId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-detail', userId, resp.target.id],
      });
      queryClient.removeQueries({
        queryKey: ['knowledge-entity-detail', userId, variables.sourceId],
      });
      options?.onSuccess?.(resp);
    },
    onError: (err) => {
      options?.onError?.(err);
    },
  });

  return {
    merge: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: mutation.error,
  };
}

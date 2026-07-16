import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type CreateEntityPayload,
  type CreateRelationPayload,
  type Entity,
  type EntityMergeErrorCode,
  type EntityMergeResponse,
  type EntityRelation,
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
  update: (args: {
    entityId: string;
    payload: EntityUpdatePayload;
    /** C9 (D-K19d-γa-01): version from the entity detail the user is
     *  editing. Sent as ``If-Match: W/"N"``. BE 428s without it. */
    ifMatchVersion: number;
  }) => Promise<Entity>;
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
    mutationFn: async (args: {
      entityId: string;
      payload: EntityUpdatePayload;
      ifMatchVersion: number;
    }) => {
      return knowledgeApi.updateEntity(
        args.entityId,
        args.payload,
        args.ifMatchVersion,
        accessToken!,
      );
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
    onError: async (err, variables) => {
      // C9: on 412 conflict, refresh the detail cache so a re-open of
      // the edit dialog sees the fresh baseline. The toast is owned
      // by the consumer via onError.
      const status = (err as Error & { status?: number }).status;
      if (status === 412) {
        await queryClient.invalidateQueries({
          queryKey: ['knowledge-entity-detail', userId, variables.entityId],
        });
      }
      options?.onError?.(err as Error);
    },
  });

  return {
    update: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}


// ── C9 (D-K19d-γa-02) — unlock user_edited ─────────────────────────

export interface UseUnlockEntityResult {
  unlock: (args: { entityId: string }) => Promise<Entity>;
  isPending: boolean;
  error: Error | null;
}

export function useUnlockEntity(options?: {
  onSuccess?: (entity: Entity) => void;
  onError?: (err: Error) => void;
}): UseUnlockEntityResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: { entityId: string }) => {
      return knowledgeApi.unlockEntity(args.entityId, accessToken!);
    },
    onSuccess: async (entity) => {
      // Same invalidation as update: list + detail, so the open panel
      // reflects user_edited=false immediately.
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
    unlock: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

// ── C9 (C9-promote-flow) — promote discovered → glossary draft + anchor ──

export interface UsePromoteEntityResult {
  promote: (args: { entityId: string }) => Promise<Entity>;
  isPending: boolean;
  error: Error | null;
}

export function usePromoteEntity(options?: {
  onSuccess?: (entity: Entity) => void;
  onError?: (err: Error) => void;
}): UsePromoteEntityResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: { entityId: string }) => {
      return knowledgeApi.promoteEntity(args.entityId, accessToken!);
    },
    onSuccess: async (entity) => {
      // The entity flipped discovered → canonical. Invalidate the browse
      // list (status glyph / sort) AND the open detail (promote button now
      // hidden, unpin now available) so both reflect the anchored state.
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
    promote: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

// ── C9 — toggle glossary context-pin (is_pinned_for_context) ─────────

export interface UseToggleGlossaryPinResult {
  toggle: (args: {
    entityId: string;
    bookId: string;
    glossaryEntityId: string;
    pinned: boolean;
  }) => Promise<boolean>;
  isPending: boolean;
  error: Error | null;
}

export function useToggleGlossaryPin(options?: {
  onSuccess?: (pinned: boolean) => void;
  onError?: (err: Error) => void;
}): UseToggleGlossaryPinResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: {
      entityId: string;
      bookId: string;
      glossaryEntityId: string;
      pinned: boolean;
    }) => {
      await knowledgeApi.setGlossaryEntityPinned(
        args.bookId,
        args.glossaryEntityId,
        args.pinned,
        accessToken!,
      );
      return args.pinned;
    },
    onSuccess: async (pinned, variables) => {
      // The pin state lives on the glossary entity, not the knowledge
      // entity, but refresh the detail so any pin-derived UI stays honest.
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-detail', userId, variables.entityId],
      });
      options?.onSuccess?.(pinned);
    },
    onError: (err) => {
      options?.onError?.(err as Error);
    },
  });

  return {
    toggle: mutation.mutateAsync,
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

// ── S7-1 — manual authoring: create entity / relation, archive ────────
//
// All three write over the ready T2.5 routes (createEntity/createRelation/
// archiveMyEntity). Invalidation mirrors the edit hook (list + detail) and
// adds the subgraph (graph node/edge appears without reload) + the composition
// cast/arc keys (an open Cast codex / Character-arc stays fresh — same keys
// the Lane-B knowledgeEffect handler hits, so agent AND human writes converge).

const COMPOSITION_CAST_KEY = ['composition', 'cast'] as const;
const COMPOSITION_ARC_KEY = ['composition', 'arc'] as const;

export interface UseCreateEntityResult {
  create: (payload: CreateEntityPayload) => Promise<Entity>;
  isPending: boolean;
  error: Error | null;
}

export function useCreateEntity(options?: {
  onSuccess?: (entity: Entity) => void;
  onError?: (err: Error) => void;
}): UseCreateEntityResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (payload: CreateEntityPayload) => {
      return knowledgeApi.createEntity(payload, accessToken!);
    },
    onSuccess: async (entity) => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entities', userId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-subgraph', userId],
      });
      await queryClient.invalidateQueries({ queryKey: COMPOSITION_CAST_KEY });
      options?.onSuccess?.(entity);
    },
    onError: (err) => {
      options?.onError?.(err as Error);
    },
  });

  return {
    create: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

export interface UseCreateRelationResult {
  createRelation: (payload: CreateRelationPayload) => Promise<EntityRelation>;
  isPending: boolean;
  error: Error | null;
}

export function useCreateRelation(options?: {
  onSuccess?: (relation: EntityRelation) => void;
  onError?: (err: Error) => void;
}): UseCreateRelationResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (payload: CreateRelationPayload) => {
      return knowledgeApi.createRelation(payload, accessToken!);
    },
    onSuccess: async (relation, payload) => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-subgraph', userId],
      });
      // Both endpoints' 1-hop relation lists changed.
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-detail', userId, payload.subject_id],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-detail', userId, payload.object_id],
      });
      await queryClient.invalidateQueries({ queryKey: COMPOSITION_ARC_KEY });
      options?.onSuccess?.(relation);
    },
    onError: (err) => {
      options?.onError?.(err as Error);
    },
  });

  return {
    createRelation: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

export interface UseArchiveEntityResult {
  archive: (args: { entityId: string }) => Promise<void>;
  isPending: boolean;
  error: Error | null;
}

export function useArchiveEntity(options?: {
  onSuccess?: () => void;
  onError?: (err: Error) => void;
}): UseArchiveEntityResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (args: { entityId: string }) => {
      // Soft archive (user_archived): 204 on success, 404 cross-user/typo —
      // BOTH mean "now hidden", so we do NOT treat 404 as a failure here.
      try {
        await knowledgeApi.archiveMyEntity(args.entityId, accessToken!);
      } catch (err) {
        const status = (err as Error & { status?: number }).status;
        if (status === 404) return; // idempotent: already gone == success
        throw err;
      }
    },
    onSuccess: async (_void, args) => {
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entities', userId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-entity-detail', userId, args.entityId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-subgraph', userId],
      });
      await queryClient.invalidateQueries({ queryKey: COMPOSITION_CAST_KEY });
      options?.onSuccess?.();
    },
    onError: (err) => {
      options?.onError?.(err as Error);
    },
  });

  return {
    archive: mutation.mutateAsync,
    isPending: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
  };
}

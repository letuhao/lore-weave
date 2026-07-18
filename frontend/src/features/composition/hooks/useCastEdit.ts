// s7-4 — the Cast codex / Character-arc OCC write controller. Mirrors the
// useSceneInspector serialized-write shape: rename/edit go through PATCH with a
// strict If-Match (428 without / 412 stale → the caller re-seeds the fresh row),
// create/link/archive carry no version and need none.
//
// Why a dedicated hook and not the knowledge useEntityMutations hooks? Those
// invalidate the knowledge-* keys; the cast/arc panels read the COMPOSITION
// namespace (['composition','cast'|'arc',…]). A human rename here must refresh
// THOSE caches (and the knowledge ones too, so the KG panels stay in sync), or
// the codex shows a stale version and the next rename 412s against it. This is
// the human-write mirror of the Lane-B knowledgeEffect edit (which covers the
// AGENT write path). ONE home for the invalidation set.
import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type CreateEntityPayload,
  type CreateRelationPayload,
  type Entity,
  type EntityRelation,
} from '../../knowledge/api';

const CAST_KEY = ['composition', 'cast'] as const;
const ARC_KEY = ['composition', 'arc'] as const;

export interface UseCastEditResult {
  rename: (args: {
    entityId: string;
    name: string;
    /** the row's current OCC version — sent as If-Match. */
    version: number;
  }) => Promise<Entity>;
  create: (payload: CreateEntityPayload) => Promise<Entity>;
  link: (payload: CreateRelationPayload) => Promise<EntityRelation>;
  archive: (args: { entityId: string }) => Promise<void>;
  isPending: boolean;
}

export function useCastEdit(options?: {
  onRenamed?: (e: Entity) => void;
  onRenameConflict?: () => void;
  onCreated?: (e: Entity) => void;
  onLinked?: (r: EntityRelation) => void;
  onArchived?: () => void;
  onError?: (err: Error) => void;
}): UseCastEditResult {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const invalidateAll = useCallback(async () => {
    // Refresh BOTH namespaces: composition (this panel) + knowledge (the KG
    // panels), so a write is visible everywhere regardless of who opened what.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: CAST_KEY }),
      queryClient.invalidateQueries({ queryKey: ARC_KEY }),
      queryClient.invalidateQueries({ queryKey: ['knowledge-entities'] }),
      queryClient.invalidateQueries({ queryKey: ['knowledge-entity-detail'] }),
      queryClient.invalidateQueries({ queryKey: ['knowledge-subgraph'] }),
    ]);
  }, [queryClient]);

  const renameMut = useMutation({
    mutationFn: (args: { entityId: string; name: string; version: number }) =>
      knowledgeApi.updateEntity(
        args.entityId,
        { name: args.name },
        args.version,
        accessToken!,
      ),
    onSuccess: async (entity) => {
      await invalidateAll();
      options?.onRenamed?.(entity);
    },
    onError: async (err) => {
      // On a 412 the row's version is stale — reseed the caches so the next
      // edit sees the fresh version (never clobber). Surface separately so the
      // panel can say "changed elsewhere — reloaded" without blaming the user.
      const status = (err as Error & { status?: number }).status;
      if (status === 412) {
        await invalidateAll();
        options?.onRenameConflict?.();
        return;
      }
      options?.onError?.(err as Error);
    },
  });

  const createMut = useMutation({
    mutationFn: (payload: CreateEntityPayload) =>
      knowledgeApi.createEntity(payload, accessToken!),
    onSuccess: async (entity) => {
      await invalidateAll();
      options?.onCreated?.(entity);
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  const linkMut = useMutation({
    mutationFn: (payload: CreateRelationPayload) =>
      knowledgeApi.createRelation(payload, accessToken!),
    onSuccess: async (relation) => {
      await invalidateAll();
      options?.onLinked?.(relation);
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  const archiveMut = useMutation({
    mutationFn: async (args: { entityId: string }) => {
      try {
        await knowledgeApi.archiveMyEntity(args.entityId, accessToken!);
      } catch (err) {
        // 404 == already hidden == success (idempotent soft archive).
        if ((err as Error & { status?: number }).status === 404) return;
        throw err;
      }
    },
    onSuccess: async () => {
      await invalidateAll();
      options?.onArchived?.();
    },
    onError: (err) => options?.onError?.(err as Error),
  });

  return {
    rename: renameMut.mutateAsync,
    create: createMut.mutateAsync,
    link: linkMut.mutateAsync,
    archive: archiveMut.mutateAsync,
    isPending:
      renameMut.isPending ||
      createMut.isPending ||
      linkMut.isPending ||
      archiveMut.isPending,
  };
}

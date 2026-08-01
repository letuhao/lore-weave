// The AUTHOR's half of the error-block loop (atom-edit Phase D / F3 stage 2).
//
// Phase D shipped the marks with only two live FE calls — `create` and `list`. Everything that
// CLOSES a mark (resolve / dismiss / reopen) or removes it existed on the API and on the co-writer's
// MCP tool, and nowhere the author could reach: the agent could close the author's own annotation
// and the author could not. That is the same shape as the scene-link bug this sweep already fixed
// (a capability the agent has and the human doesn't), so it is fixed the same way — a real door,
// and a soft delete that owes an Undo gets one.
//
// Controller only: owns the mutations + cache invalidation, renders nothing.
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { errorBlocksApi, type ErrorBlock } from '../errorBlocks';

export interface ErrorBlockActions {
  resolve: (blockId: string, resolution?: string) => void;
  dismiss: (blockId: string, resolution?: string) => void;
  reopen: (blockId: string) => void;
  /** Soft-archives the mark. `onRemoved` fires with the id so the caller can offer the Undo —
   *  the list read filters archived rows, so once the toast is gone the id is unreachable. */
  remove: (blockId: string, onRemoved: (id: string) => void) => void;
  restore: (blockId: string, onFailed?: (status?: number) => void) => void;
  busy: boolean;
}

export function useErrorBlockActions(
  projectId: string | null,
  chapterId: string | null,
  token: string | null,
): ErrorBlockActions {
  const qc = useQueryClient();
  // The exact key `useErrorBlockMarks` reads, so a close re-renders the decorations too — a mark
  // that stays highlighted after the author resolves it reads as "the click did nothing".
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['composition', 'error-blocks', projectId, chapterId] });
  };

  const close = useMutation({
    mutationFn: (v: { id: string; op: 'resolve' | 'dismiss'; resolution?: string }) =>
      v.op === 'resolve'
        ? errorBlocksApi.resolve(v.id, token!, { resolution: v.resolution })
        : errorBlocksApi.dismiss(v.id, token!, { resolution: v.resolution }),
    onSuccess: invalidate,
  });
  const reopenM = useMutation({
    mutationFn: (id: string) => errorBlocksApi.reopen(id, token!),
    onSuccess: invalidate,
  });
  const removeM = useMutation({
    mutationFn: (id: string) => errorBlocksApi.remove(id, token!),
    onSuccess: invalidate,
  });
  const restoreM = useMutation({
    mutationFn: (id: string) => errorBlocksApi.restore(id, token!),
    onSuccess: invalidate,
  });

  return {
    resolve: (id, resolution) => close.mutate({ id, op: 'resolve', resolution }),
    dismiss: (id, resolution) => close.mutate({ id, op: 'dismiss', resolution }),
    reopen: (id) => reopenM.mutate(id),
    remove: (id, onRemoved) => removeM.mutate(id, { onSuccess: () => onRemoved(id) }),
    restore: (id, onFailed) =>
      restoreM.mutate(id, { onError: (e) => onFailed?.((e as { status?: number }).status) }),
    busy: close.isPending || reopenM.isPending || removeM.isPending || restoreM.isPending,
  };
}

/** Rows the author should be offered actions for, newest first. `orphaned` is included on
 *  purpose — the prose it pointed at changed, so it can no longer be drawn in the document, and
 *  the list is then the ONLY place it exists. Dropping it here would strand the mark forever. */
export function actionableBlocks(blocks: ErrorBlock[]): ErrorBlock[] {
  return blocks.filter((b) => b.status === 'open' || b.status === 'proposed' || b.status === 'orphaned');
}

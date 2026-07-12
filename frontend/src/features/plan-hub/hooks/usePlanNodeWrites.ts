// 24 H3 / PH20 — the DRAWER's write half.
//
// PH16 fixes the click contract: "the drawer edits the DESIRED state; 'Open in Editor' goes to the
// ACTUAL." So everything here writes the spec (`outline_node`), and nothing here touches prose.
//
// OCC is the existing `If-Match: <version>` header convention (PH20/F-H3 — ONE OCC concept, one name
// per surface). A 412 comes back with the CURRENT row, so the recovery is "reload + tell the user",
// never a silent clobber (the SceneRail precedent).
//
// ARCHIVE is Tier-A-shaped: it has a VERIFIED inverse (`restoreNode`, which also un-archives the
// ancestor chain so the node reconnects to a visible root). Reversibility is what licenses an
// immediate write with an undo, rather than a confirm dialog — 07S §5.
import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { archiveNode, patchNode, restoreNode, type NodeEdit } from '../api';

export interface NodeWriteUndo {
  label: string;
  run: () => void;
}

export interface PlanNodeWrites {
  /** Patch spec fields on the selected node. OCC'd on `version`. */
  edit: (nodeId: string, version: number, patch: NodeEdit) => void;
  /** Soft-delete the node (its subtree goes with it). Undoable. */
  archive: (nodeId: string) => void;
  restore: (nodeId: string) => void;
  saving: boolean;
  error: string | null;
  undo: NodeWriteUndo | null;
  clearError: () => void;
}

export function usePlanNodeWrites(
  bookId: string,
  token: string | null,
  /** Refetch the hand-rolled window slices. react-query's invalidate CANNOT reach them, and they
   *  hold the very rows an edit mutates (title/status/version) — the bug H5 shipped once. */
  reloadWindows: () => void,
): PlanNodeWrites {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [undo, setUndo] = useState<NodeWriteUndo | null>(null);

  const settle = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['plan-hub'] });
    // The drawer reads the node through `compositionApi.getNode` under its own key — invalidate that
    // too, or the drawer keeps showing the pre-edit row it just wrote.
    void qc.invalidateQueries({ queryKey: ['composition', 'node'] });
    reloadWindows();
  }, [qc, reloadWindows]);

  const onFailed = useCallback((e: unknown) => {
    const err = e as Error & { status?: number };
    if (err?.status === 412) {
      // The row moved under us. The settle has already reloaded it, so say we re-synced — never
      // "your edit was lost", and never silently overwrite the other writer.
      setError('That node changed elsewhere — the drawer reloaded. Make the edit again.');
      return;
    }
    setError(err?.message || 'Could not save.');
  }, []);

  const editMutation = useMutation({
    mutationFn: (v: { nodeId: string; version: number; patch: NodeEdit }) =>
      patchNode(v.nodeId, v.patch, v.version, token!),
    onError: onFailed,
    onSettled: settle,
  });

  const archiveMutation = useMutation({
    mutationFn: (nodeId: string) => archiveNode(nodeId, token!),
    onError: onFailed,
    onSettled: settle,
  });

  const restoreMutation = useMutation({
    mutationFn: (nodeId: string) => restoreNode(nodeId, token!),
    onError: onFailed,
    onSettled: settle,
  });

  const edit = useCallback(
    (nodeId: string, version: number, patch: NodeEdit) => {
      if (!token) return;
      // An empty patch is not a no-op to be silently swallowed — it is a caller bug. But firing it
      // would still bump the version and 412 the next real edit, so drop it here, loudly in code.
      if (Object.keys(patch).length === 0) return;
      setError(null);
      setUndo(null); // an edit's inverse needs the PRIOR value; the drawer supplies it (below)
      editMutation.mutate({ nodeId, version, patch });
    },
    [token, editMutation],
  );

  const archive = useCallback(
    (nodeId: string) => {
      if (!token) return;
      setError(null);
      archiveMutation.mutate(nodeId, {
        onSuccess: () => {
          setUndo({
            label: 'Archived',
            run: () => restoreMutation.mutate(nodeId),
          });
        },
      });
    },
    [token, archiveMutation, restoreMutation],
  );

  const restore = useCallback(
    (nodeId: string) => {
      if (!token) return;
      setError(null);
      setUndo(null);
      restoreMutation.mutate(nodeId);
    },
    [token, restoreMutation],
  );

  return {
    edit,
    archive,
    restore,
    saving: editMutation.isPending || archiveMutation.isPending || restoreMutation.isPending,
    error,
    undo,
    clearError: useCallback(() => setError(null), []),
  };
}

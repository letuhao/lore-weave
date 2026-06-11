// LOOM Composition (T1.1a/b) — committed-outline read + node-CRUD controller
// (react-query). T1.1a is the read query; T1.1b adds the tree mutations (rename /
// add-child / archive / set-status). Reorder + cards mode land in T1.1c/d.
// Mirrors useCanonRules.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { OutlineNode } from '../types';

export function useOutline(projectId: string | undefined, token: string | null, includeArchived = false) {
  return useQuery({
    // Key includes the flag so the archived view caches separately from the
    // default view (and a mutation invalidating the base key — without the flag —
    // still refetches both via prefix match).
    queryKey: ['composition', 'outline', projectId, includeArchived],
    queryFn: () => compositionApi.getOutline(projectId!, token!, includeArchived),
    enabled: !!projectId && !!token,
    // Toggling the archived view changes the key; keep the prior rows on screen
    // during the swap so the whole panel (header + toggle) doesn't flash "Loading".
    placeholderData: keepPreviousData,
    select: (d): OutlineNode[] => d.nodes,
  });
}

/**
 * T1.1b — outline tree node CRUD. `rename`/`setStatus` send the node's `version`
 * as If-Match → a concurrent edit 412s (NODE_VERSION_CONFLICT); the caller's
 * onError surfaces it + refetches. `setStatus` also invalidates the publish-gate
 * (a scene → 'done' commits it, same as M9 useSetSceneStatus). `addChild`
 * creates a scene under a chapter (carrying chapter_id) or a beat under a scene.
 */
export function useOutlineMutations(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  const key = ['composition', 'outline', projectId];
  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const rename = useMutation({
    mutationFn: (v: { nodeId: string; title: string; version: number }) =>
      compositionApi.patchNode(v.nodeId, { title: v.title }, token!, v.version),
    onSuccess: invalidate,
  });
  const setStatus = useMutation({
    mutationFn: (v: { nodeId: string; status: OutlineNode['status']; version: number }) =>
      compositionApi.patchNode(v.nodeId, { status: v.status }, token!, v.version),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ['composition', 'publish-gate', projectId] });
    },
  });
  // T1.1d — edit a card's text (title + synopsis) in one patch, If-Match guarded.
  const editCard = useMutation({
    mutationFn: (v: { nodeId: string; title: string; synopsis: string; version: number }) =>
      compositionApi.patchNode(v.nodeId, { title: v.title, synopsis: v.synopsis }, token!, v.version),
    onSuccess: invalidate,
  });
  // T1.2 Beat Sheet — assign (or clear, beatRole=null) a node's beat_role.
  const setBeatRole = useMutation({
    mutationFn: (v: { nodeId: string; beatRole: string | null; version: number }) =>
      compositionApi.patchNode(v.nodeId, { beat_role: v.beatRole }, token!, v.version),
    onSuccess: invalidate,
  });
  const addChild = useMutation({
    mutationFn: (v: { kind: 'scene' | 'beat'; parent_id: string; chapter_id?: string | null; title: string }) =>
      compositionApi.createNode(
        projectId!,
        { kind: v.kind, parent_id: v.parent_id, chapter_id: v.chapter_id ?? null, title: v.title },
        token!,
      ),
    onSuccess: invalidate,
  });
  const archive = useMutation({
    mutationFn: (nodeId: string) => compositionApi.archiveNode(nodeId, token!),
    onSuccess: invalidate,
  });
  const restore = useMutation({
    mutationFn: (nodeId: string) => compositionApi.restoreNode(nodeId, token!),
    onSuccess: invalidate,
  });
  const reorder = useMutation({
    mutationFn: (v: { nodeId: string; new_parent_id: string | null; after_id: string | null; version: number }) =>
      compositionApi.reorderNode(v.nodeId, { new_parent_id: v.new_parent_id, after_id: v.after_id }, token!, v.version),
    // Also invalidate the publish-gate: a cross-chapter scene reparent changes
    // scenes_total for BOTH the source + destination chapters (same rule as
    // setStatus, which changes scenes_done).
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ['composition', 'publish-gate', projectId] });
    },
  });

  return { rename, setStatus, editCard, setBeatRole, addChild, archive, restore, reorder, invalidate };
}

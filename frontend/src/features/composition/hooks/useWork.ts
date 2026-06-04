// LOOM Composition (M8) — Work resolution/create + scene + grounding controllers.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi } from '../api';
import type { OutlineNode } from '../types';

export function useWorkResolution(bookId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: ['composition', 'work', bookId],
    queryFn: () => compositionApi.resolveWork(bookId!, token!),
    enabled: !!bookId && !!token,
  });
}

export function useCreateWork(bookId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => compositionApi.createWork(bookId!, token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] }),
  });
}

/** The current chapter's scenes, derived from the project outline. */
export function useChapterScenes(
  projectId: string | undefined, chapterId: string | undefined, token: string | null,
) {
  return useQuery({
    queryKey: ['composition', 'outline', projectId],
    queryFn: () => compositionApi.getOutline(projectId!, token!),
    enabled: !!projectId && !!token,
    select: (d): OutlineNode[] =>
      d.nodes.filter((n) => n.kind === 'scene' && n.chapter_id === chapterId),
  });
}

export function useCreateScene(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { chapter_id: string; title: string; story_order?: number }) =>
      compositionApi.createNode(projectId!, { kind: 'scene', ...payload }, token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['composition', 'outline', projectId] }),
  });
}

/**
 * Set a scene's status (M9). Marking a scene 'done' commits it for the
 * chapter-gate. Invalidates BOTH the outline (status badge) AND the publish-gate
 * (so the chapter editor's Publish affordance re-evaluates) — without the
 * publish-gate invalidation the gate would stay stale until a remount.
 */
export function useSetSceneStatus(projectId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { nodeId: string; status: OutlineNode['status'] }) =>
      compositionApi.patchNode(vars.nodeId, { status: vars.status }, token!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['composition', 'outline', projectId] });
      qc.invalidateQueries({ queryKey: ['composition', 'publish-gate', projectId] });
    },
  });
}

export function useGrounding(
  projectId: string | undefined, nodeId: string | undefined, guide: string,
  token: string | null, enabled: boolean,
) {
  return useQuery({
    queryKey: ['composition', 'grounding', projectId, nodeId, guide],
    queryFn: () => compositionApi.getGrounding(projectId!, nodeId!, guide, token!),
    enabled: !!projectId && !!nodeId && !!token && enabled,
  });
}

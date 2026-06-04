// LOOM Composition (M9) — chapter-gate controller (OI-1 publish wiring).
//
// Surfaces whether a chapter may be published: composition blocks the (CM-FE)
// Publish affordance until ALL the chapter's scenes are 'done', so no
// unreviewed AI scene is canonized. The gate ONLY applies to books that have a
// real composition Work (status 'found'/'candidates'); a Classic-only book has
// no Work → blocked:false → CM-FE's publish stays ungated.
import { useQuery } from '@tanstack/react-query';
import { compositionApi } from '../api';
import { useWorkResolution } from './useWork';

export function usePublishGate(
  projectId: string | undefined, chapterId: string | undefined,
  token: string | null, enabled: boolean,
) {
  return useQuery({
    queryKey: ['composition', 'publish-gate', projectId, chapterId],
    queryFn: () => compositionApi.publishGate(projectId!, chapterId!, token!),
    enabled: !!projectId && !!chapterId && !!token && enabled,
  });
}

export type ChapterPublishGate = {
  /** True → the Publish affordance should be disabled. */
  blocked: boolean;
  scenesTotal: number;
  scenesDone: number;
};

/**
 * Composes Work resolution + the chapter gate into a single signal for the
 * editor toolbar. Returns blocked:false (ungated) whenever there is no
 * composition Work, while resolution/gate is loading, or on error — publishing
 * is a book-service call and the gate is a UX affordance, so degrading open is
 * correct (and preserves CM-FE for Classic-only books).
 */
export function useChapterPublishGate(
  bookId: string | undefined, chapterId: string | undefined, token: string | null,
): ChapterPublishGate {
  const resolution = useWorkResolution(bookId, token);
  const res = resolution.data;
  // A real composition_work exists only for 'found' / 'candidates' (mirrors
  // CompositionPanel's `work` derivation). Other statuses = no Work → ungated.
  const work =
    res?.status === 'found' ? res.work : res?.status === 'candidates' ? (res.candidates[0] ?? null) : null;
  const projectId = work?.project_id;

  const gate = usePublishGate(projectId, chapterId, token, !!projectId);
  const g = gate.data;

  if (!projectId || !g) return { blocked: false, scenesTotal: 0, scenesDone: 0 };
  return { blocked: !g.can_publish, scenesTotal: g.scenes_total, scenesDone: g.scenes_done };
}

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
import { useActiveWorkId } from './useActiveWork';
import { resolveActiveWork } from '../workSelect';

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
  // A2-S4b — the canon dimensions of the gate. `canonBlocked` is part of why
  // `blocked` is true (a confirmed contradiction, HARD); `canonUncheckedScenes`
  // is a NON-blocking warning (canon couldn't be verified — dirty data).
  canonBlocked: boolean;
  canonUnresolvedScenes: number;
  canonUncheckedScenes: number;
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
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  // A real composition_work exists only for 'found' / 'candidates'. Resolve the
  // ACTIVE Work (EC-3d: the user's per-book pref, else canonical) so the gate follows
  // a "Switch to". Other statuses = no Work → ungated.
  const work = resolveActiveWork(resolution.data, activeWorkId);
  const projectId = work?.project_id;

  const gate = usePublishGate(projectId, chapterId, token, !!projectId);
  const g = gate.data;

  // Degrade-open: no Work / loading / error → ungated, zero canon signal.
  if (!projectId || !g)
    return {
      blocked: false, scenesTotal: 0, scenesDone: 0,
      canonBlocked: false, canonUnresolvedScenes: 0, canonUncheckedScenes: 0,
    };
  return {
    blocked: !g.can_publish, scenesTotal: g.scenes_total, scenesDone: g.scenes_done,
    canonBlocked: !!g.canon_blocked,
    canonUnresolvedScenes: g.canon_unresolved_scenes ?? 0,
    canonUncheckedScenes: g.canon_unchecked_scenes ?? 0,
  };
}

/**
 * A2-S4b — derive the editor-toolbar publish messages from the gate (pure, so it
 * unit-tests without rendering the page). Returns:
 *  - `blockedReason`  — the disabled-Publish tooltip. When BOTH scenes are pending
 *    AND a canon contradiction is unresolved, the two are COMBINED (PO decision),
 *    joined with '; '. `undefined` when not blocked (or no concrete reason → open).
 *  - `uncheckedWarning` — a NON-blocking notice ("canon unverified in N scenes",
 *    dirty data); independent of `blocked` since `can_publish` ignores unchecked.
 * `t` is injected (editor namespace) so callers keep i18n in the view layer.
 */
export function publishGateMessages(
  gate: ChapterPublishGate,
  t: (key: string, opts?: Record<string, unknown>) => string,
): { blockedReason?: string; uncheckedWarning?: string } {
  const uncheckedWarning =
    gate.canonUncheckedScenes > 0
      ? t('publish.gate_unchecked', { count: gate.canonUncheckedScenes })
      : undefined;

  if (!gate.blocked) return { blockedReason: undefined, uncheckedWarning };
  if (gate.scenesTotal === 0) return { blockedReason: t('publish.gate_no_scenes'), uncheckedWarning };

  const parts: string[] = [];
  if (gate.scenesDone < gate.scenesTotal) {
    parts.push(t('publish.gate_pending', { pending: gate.scenesTotal - gate.scenesDone, total: gate.scenesTotal }));
  }
  if (gate.canonBlocked) {
    parts.push(t('publish.gate_canon_blocked', { count: gate.canonUnresolvedScenes }));
  }
  // Empty join (blocked for a reason we don't model) → undefined = degrade open.
  return { blockedReason: parts.join('; ') || undefined, uncheckedWarning };
}

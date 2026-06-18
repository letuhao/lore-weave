// LOOM Composition (M8) — Work resolution/create + scene + grounding controllers.
import { useEffect, useState } from 'react';
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

/**
 * D-C16: self-healing resolver for a PENDING null-project Work. When POST /work
 * returns a greenfield Work created during a knowledge-service outage (project_id
 * null + pending_project_backfill), the resolution query can't surface it — it
 * excludes pending works — so the panel holds the Work's surrogate id and this
 * hook polls resolve-project until the knowledge project is backfilled, then
 * invalidates the work query so the now-backed Work flows in. Bounded backoff;
 * gives up to a `failed` state the UI offers a retry for.
 *
 * The poll is a SYNCHRONIZATION effect (drive an external retry loop until a
 * condition holds) — NOT a reaction to a user action. The user action (clicking
 * "Set up co-writer") calls start() directly from the create handler.
 */
export function usePendingWorkResolver(
  bookId: string | undefined, token: string | null,
) {
  const qc = useQueryClient();
  // `round` lets retry() re-arm the SAME id (a new object → the effect re-runs).
  const [target, setTarget] = useState<{ id: string; round: number } | null>(null);
  const [state, setState] = useState<'idle' | 'resolving' | 'failed'>('idle');

  useEffect(() => {
    if (!target || !token) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let attempt = 0;
    const MAX_ATTEMPTS = 8;
    setState('resolving');
    const tick = async () => {
      attempt += 1;
      try {
        const w = await compositionApi.resolveWorkProject(target.id, token);
        if (cancelled) return;
        if (w.project_id) {
          setState('idle');
          setTarget(null);
          qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] });
          return;
        }
      } catch {
        // 409 STILL_PENDING (knowledge still down) or a transient error → keep
        // polling until the attempt cap, then surface a retry.
      }
      if (cancelled) return;
      if (attempt >= MAX_ATTEMPTS) { setState('failed'); return; }
      timer = setTimeout(tick, Math.min(500 * 2 ** (attempt - 1), 5000));
    };
    timer = setTimeout(tick, 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [target, token, bookId, qc]);

  return {
    state,
    /** Begin resolving a pending Work by its surrogate id (from the create handler). */
    start: (workId: string) => setTarget({ id: workId, round: 0 }),
    /** Re-arm after a give-up. */
    retry: () => setTarget((t) => (t ? { id: t.id, round: t.round + 1 } : t)),
  };
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

/**
 * Merge a partial patch over the work's settings and persist it (the server
 * REPLACES the whole settings blob, so we MUST merge — same rule as
 * useSetAssemblyMode, generalized). Invalidates the work query (keyed by bookId)
 * so every consumer reflects the persisted value. Used by the Settings sub-tab to
 * toggle narrative_thread_enabled / assembly_mode / default_model_ref without
 * dropping the other keys.
 */
export function useSetWorkSettings(bookId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { projectId: string; currentSettings: Record<string, unknown>; patch: Record<string, unknown> }) =>
      compositionApi.patchWork(v.projectId, { settings: { ...v.currentSettings, ...v.patch } }, token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] }),
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

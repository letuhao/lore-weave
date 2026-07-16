// 22-C3 controller — the scene-inspector's logic (no JSX). A detail-over-selection pane (SC10):
// it reads the studio bus's active scene (an outline_node id), fetches that node's FULL fields
// (the summary projections drop the intent/craft fields it edits), and patches them with OCC
// (If-Match version → 412 "changed elsewhere, reloaded"), the same domain path SceneRail uses.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { useStudioBusSelector } from '../host/StudioHostProvider';

export type SceneInspectorState = {
  node: OutlineNode | null;
  projectId: string | null;
  loading: boolean;
  error: string | null;
  saving: boolean;
  /** OCC patch: writes the fields, on 412 reloads the fresh node so the next edit lands. */
  patch: (p: Partial<OutlineNode>) => Promise<void>;
};

export function useSceneInspector(bookId: string | null): SceneInspectorState {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const activeSceneId = useStudioBusSelector((s) => s.activeSceneId);
  const work = useWorkResolution(bookId ?? '', token);
  const { data: activeWorkId } = useActiveWorkId(bookId ?? '', token);

  // EC-3d: the ACTIVE Work's project (per-book pref, else canonical) — NOT candidates[0].
  const projectId = useMemo(
    () => resolveActiveWork(work.data, activeWorkId)?.project_id ?? null,
    [work.data, activeWorkId],
  );

  const [node, setNode] = useState<OutlineNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gen = useRef(0);
  // A live mirror of `node` so a serialized patch reads the FRESH version (not its closure's stale
  // one), and a chain so back-to-back edits run one-at-a-time (review: OCC single-flight race —
  // EntityRefField commits on every change, so two rapid Cast&Setting edits both sent If-Match v1 →
  // the 2nd 412'd → silently dropped + a false "changed elsewhere"; chaining lets the 2nd see v2).
  const nodeRef = useRef<OutlineNode | null>(null);
  useEffect(() => { nodeRef.current = node; }, [node]);
  const chainRef = useRef<Promise<void>>(Promise.resolve());

  const load = useCallback(async () => {
    if (!token || !projectId || !activeSceneId) { setNode(null); return; }
    const myGen = ++gen.current;
    setLoading(true); setError(null);
    try {
      const n = await compositionApi.getNode(activeSceneId, token);
      if (myGen === gen.current) setNode(n);
    } catch (e) {
      if (myGen === gen.current) { setNode(null); setError(e instanceof Error ? e.message : 'Failed to load scene'); }
    } finally {
      if (myGen === gen.current) setLoading(false);
    }
  }, [token, projectId, activeSceneId]);

  // Reload whenever the selected scene (or its Work) changes.
  useEffect(() => { void load(); }, [load]);

  const patch = useCallback((p: Partial<OutlineNode>): Promise<void> => {
    // Capture the scene under edit NOW; if the selection moves before this link of the chain runs,
    // the edit was for a scene no longer shown — drop it (applying it to the new scene is the bug).
    const targetId = nodeRef.current?.id ?? null;
    const run = async () => {
      const current = nodeRef.current;
      if (!token || !current || current.id !== targetId) return;
      setSaving(true); setError(null);
      try {
        // Read the version from the mirror, not a closure — the prior chained patch already bumped it.
        const updated = await compositionApi.patchNode(current.id, p, token, current.version);
        nodeRef.current = updated; setNode(updated);
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 412) {
          // A genuine external change (our own back-to-back edits no longer collide — they chain).
          // Pull the fresh version so the next edit lands (SceneRail's pattern). Reload INLINE with
          // the current scope so a lagging closure can never blank the pane.
          setError('changed elsewhere — reloaded');
          if (projectId && activeSceneId) {
            try {
              const gen0 = ++gen.current;
              const fresh = await compositionApi.getNode(activeSceneId, token);
              if (gen0 === gen.current) { nodeRef.current = fresh; setNode(fresh); }
            } catch { /* leave the stale node + the conflict message; a manual reselect re-fetches */ }
          }
        } else {
          setError(e instanceof Error ? e.message : 'Failed to save');
        }
      } finally {
        setSaving(false);
      }
    };
    // Single-flight: chain after any in-flight patch (regardless of its outcome) so writes serialize.
    const next = chainRef.current.then(run, run);
    chainRef.current = next;
    return next;
  }, [token, projectId, activeSceneId]);

  return { node, projectId, loading, error, saving, patch };
}

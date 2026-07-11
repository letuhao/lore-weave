// 22-C3 controller — the scene-inspector's logic (no JSX). A detail-over-selection pane (SC10):
// it reads the studio bus's active scene (an outline_node id), fetches that node's FULL fields
// (the summary projections drop the intent/craft fields it edits), and patches them with OCC
// (If-Match version → 412 "changed elsewhere, reloaded"), the same domain path SceneRail uses.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { compositionApi } from '@/features/composition/api';
import type { OutlineNode } from '@/features/composition/types';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
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

  const projectId = useMemo(() => {
    const d = work.data;
    if (d?.status === 'found') return d.work?.project_id ?? null;
    if (d?.status === 'candidates') return d.candidates[0]?.project_id ?? null;
    return null;
  }, [work.data]);

  const [node, setNode] = useState<OutlineNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gen = useRef(0);

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

  const patch = useCallback(async (p: Partial<OutlineNode>) => {
    if (!token || !node) return;
    setSaving(true); setError(null);
    try {
      const updated = await compositionApi.patchNode(node.id, p, token, node.version);
      setNode(updated);
    } catch (e) {
      const status = (e as { status?: number }).status;
      if (status === 412) {
        // Someone else changed it — pull the fresh version so the next edit lands (SceneRail's
        // pattern). Reload INLINE with the current scope (projectId/activeSceneId in this callback's
        // deps) rather than a closed-over `load`, so a lagging closure can never blank the pane.
        setError('changed elsewhere — reloaded');
        if (projectId && activeSceneId) {
          try {
            const gen0 = ++gen.current;
            const fresh = await compositionApi.getNode(activeSceneId, token);
            if (gen0 === gen.current) setNode(fresh);
          } catch { /* leave the stale node + the conflict message; a manual reselect re-fetches */ }
        }
      } else {
        setError(e instanceof Error ? e.message : 'Failed to save');
      }
    } finally {
      setSaving(false);
    }
  }, [token, node, projectId, activeSceneId]);

  return { node, projectId, loading, error, saving, patch };
}

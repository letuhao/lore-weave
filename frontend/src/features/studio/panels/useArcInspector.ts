// 32 arc-inspector — the CONTROLLER (no JSX). A detail-pane-over-a-selection (AI-1), like
// scene-inspector: the subject resolves props.params.arcId → bus.activeArcId → an in-panel
// picker, so a bare-id open is never a dead panel. Reads GET /arcs/{id} (the resolved cascade +
// the BE-A1 dense-ranked derived block + open-promise rollup); writes with OCC (If-Match → 412
// "changed elsewhere — reloaded"), mirroring useSceneInspector's serialized single-flight chain.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/auth';
import { useStudioBusSelector } from '../host/StudioHostProvider';
import { getArc, getArcs, patchArc, archiveArc, restoreArc, type ArcEdit } from '@/features/plan-hub/api';
import type { ArcDetail, ArcListNode } from '@/features/plan-hub/types';

/** The deep-link params `ui_open_studio_panel`/plan-hub can pass (32 AI-1 — same seam as
 *  quality-canon's focusRuleId). Absent ⇒ the panel falls back to the bus, then its picker. */
export interface ArcFocusParams {
  arcId?: string;
}

export interface ArcInspectorState {
  /** The resolved subject id (params → bus → picker), or null when nothing is selected. */
  arcId: string | null;
  select: (id: string | null) => void;
  /** The whole book's arc shell — the picker options, the breadcrumb, the archive blast radius. */
  shell: ArcListNode[];
  detail: ArcDetail | null;
  loading: boolean;
  error: string | null;
  saving: boolean;
  writeError: string | null;
  /** OCC edit — serialized; on 412 reloads the fresh row so the next edit lands. */
  edit: (patch: ArcEdit) => Promise<void>;
  archive: () => Promise<void>;
  restore: () => Promise<void>;
  /** root(saga)→…→self titles (breadcrumb), from the shell. */
  ancestors: ArcListNode[];
  /** how many DESCENDANT arcs an archive would take (client-derived from the shell — the DELETE
   *  response carries no count, OUT-5). */
  blastRadius: number;
}

function computeAncestors(shell: ArcListNode[], id: string | null): ArcListNode[] {
  if (!id) return [];
  const byId = new Map(shell.map((n) => [n.id, n]));
  const chain: ArcListNode[] = [];
  let cur = byId.get(id) ?? null;
  for (let hops = 0; cur && hops < 8; hops++) {
    chain.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) ?? null : null;
  }
  return chain;
}

function computeBlastRadius(shell: ArcListNode[], id: string | null): number {
  if (!id) return 0;
  const childrenOf = new Map<string, string[]>();
  for (const n of shell) {
    if (!n.parent_id) continue;
    (childrenOf.get(n.parent_id) ?? childrenOf.set(n.parent_id, []).get(n.parent_id)!).push(n.id);
  }
  let count = 0;
  const stack = [...(childrenOf.get(id) ?? [])];
  while (stack.length) {
    const next = stack.pop()!;
    count += 1;
    stack.push(...(childrenOf.get(next) ?? []));
  }
  return count;
}

export function useArcInspector(bookId: string, paramsArcId?: string): ArcInspectorState {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const qc = useQueryClient();
  const busArcId = useStudioBusSelector((s) => s.activeArcId);

  // Subject resolution precedence: an explicit in-panel pick > the deep-link param > the bus.
  const [picked, setPicked] = useState<string | null>(null);
  const arcId = picked ?? paramsArcId ?? busArcId ?? null;

  const shellQuery = useQuery({
    queryKey: ['plan-hub', 'arcs', bookId],
    queryFn: () => getArcs(bookId, token!),
    enabled: !!token && !!bookId,
  });
  const shell = useMemo(() => shellQuery.data?.arcs ?? [], [shellQuery.data]);

  const detailQuery = useQuery({
    queryKey: ['composition', 'arc', arcId],
    queryFn: () => getArc(arcId!, token!),
    enabled: !!token && !!arcId,
  });
  const detail = detailQuery.data ?? null;

  const [saving, setSaving] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  // Live mirror + single-flight chain (useSceneInspector's OCC race fix): back-to-back edits must
  // serialize so the 2nd reads the version the 1st bumped, not a stale closure.
  const detailRef = useRef<ArcDetail | null>(null);
  useEffect(() => { detailRef.current = detail; }, [detail]);
  const chainRef = useRef<Promise<void>>(Promise.resolve());

  const setDetail = useCallback((d: ArcDetail) => {
    detailRef.current = d;
    qc.setQueryData(['composition', 'arc', d.id], d);
  }, [qc]);

  const edit = useCallback((patch: ArcEdit): Promise<void> => {
    const targetId = detailRef.current?.id ?? null;
    const run = async () => {
      const current = detailRef.current;
      if (!token || !current || current.id !== targetId) return;
      setSaving(true); setWriteError(null);
      try {
        // PATCH /arcs/{id} returns the BARE node (no `resolved`/`open_promises`/derived block).
        // Seeding that straight into `detail` would blank the cascade the body reads (d.resolved)
        // and, worse, an Override edit changes `resolved` itself — so refetch the ENRICHED detail.
        // The refetched row also carries the bumped version the next chained edit needs.
        await patchArc(current.id, patch, current.version, token);
        const fresh = await getArc(current.id, token);
        setDetail(fresh);
        void qc.invalidateQueries({ queryKey: ['plan-hub', 'arcs', bookId] });
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 412 && token && targetId) {
          setWriteError('changed elsewhere — reloaded');
          try {
            const fresh = await getArc(targetId, token);
            setDetail(fresh);
          } catch { /* keep the stale row + the message; a reselect re-fetches */ }
        } else {
          setWriteError(e instanceof Error ? e.message : 'Failed to save');
        }
      } finally {
        setSaving(false);
      }
    };
    const next = chainRef.current.then(run, run);
    chainRef.current = next;
    return next;
  }, [token, bookId, qc, setDetail]);

  const archive = useCallback(async () => {
    const id = detailRef.current?.id;
    if (!token || !id) return;
    setSaving(true); setWriteError(null);
    try {
      await archiveArc(id, token);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['plan-hub'] }),
        qc.invalidateQueries({ queryKey: ['composition', 'arc', id] }),
      ]);
    } catch (e) {
      setWriteError(e instanceof Error ? e.message : 'Failed to archive');
    } finally {
      setSaving(false);
    }
  }, [token, qc]);

  const restore = useCallback(async () => {
    const id = detailRef.current?.id;
    if (!token || !id) return;
    setSaving(true); setWriteError(null);
    try {
      await restoreArc(id, token);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['plan-hub'] }),
        qc.invalidateQueries({ queryKey: ['composition', 'arc', id] }),
      ]);
    } catch (e) {
      setWriteError(e instanceof Error ? e.message : 'Failed to restore');
    } finally {
      setSaving(false);
    }
  }, [token, qc]);

  const loading = (!!arcId && detailQuery.isFetching && !detailQuery.data) ||
    (shellQuery.isFetching && !shellQuery.data);
  const error = detailQuery.error instanceof Error ? detailQuery.error.message : null;

  return {
    arcId,
    select: setPicked,
    shell,
    detail,
    loading,
    error,
    saving,
    writeError,
    edit,
    archive,
    restore,
    ancestors: useMemo(() => computeAncestors(shell, arcId), [shell, arcId]),
    blastRadius: useMemo(() => computeBlastRadius(shell, arcId), [shell, arcId]),
  };
}

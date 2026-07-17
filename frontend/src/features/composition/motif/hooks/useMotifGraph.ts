// Wave-4 (D-MOTIF-GRAPH-CANVAS) — the book motif-graph controller: the nodes+edges+layout
// query, plus the per-viewer position PERSISTENCE (a pending-map, a debounced batch flush, an
// optimistic cache update, and a fail-soft OCC 412 reseed). The canvas is a dumb view over this.
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { motifApi } from '../api';
import type { MotifGraphData, MotifGraphMove } from '../api';

const DEBOUNCE_MS = 400;

type XY = { x: number; y: number };

export function useMotifGraph(bookId: string | null, token: string | null) {
  const qc = useQueryClient();
  const key = useMemo(() => ['composition', 'motif-graph', bookId] as const, [bookId]);

  const q = useQuery({
    queryKey: key,
    queryFn: () => motifApi.motifGraph(bookId!, token!),
    enabled: !!bookId && !!token,
    staleTime: 30_000,
  });

  // Refs so the debounced flush reads the LATEST version + pending moves, never a stale closure
  // (the debounced-write-must-bind-its-target lesson).
  const versionRef = useRef(0);
  const pending = useRef<Map<string, XY>>(new Map());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (q.data) versionRef.current = q.data.layout.version;
  }, [q.data?.layout.version]);

  const flush = useCallback(async () => {
    if (!bookId || !token || pending.current.size === 0) return;
    const moves: MotifGraphMove[] = [...pending.current.entries()].map(([motif_id, p]) => ({ motif_id, x: p.x, y: p.y }));
    pending.current.clear();
    try {
      const res = await motifApi.patchGraphLayout(bookId, moves, versionRef.current, token);
      versionRef.current = res.version;
      qc.setQueryData<MotifGraphData>(key, (old) => (old ? { ...old, layout: res } : old));
    } catch (e) {
      const status = (e as { status?: number }).status;
      const current = (e as { body?: { detail?: { current?: { positions: Record<string, XY>; version: number } } } })
        .body?.detail?.current;
      if (status === 412 && current) {
        // Fail-soft: reseed from the server state, re-apply THIS drag on top (the user's move wins
        // over the other device's older state), and retry — never hard-fail a cosmetic write.
        versionRef.current = current.version;
        const mine = Object.fromEntries(moves.map((m) => [m.motif_id, { x: m.x, y: m.y }]));
        for (const m of moves) pending.current.set(m.motif_id, { x: m.x, y: m.y });
        qc.setQueryData<MotifGraphData>(key, (old) => (old
          ? { ...old, layout: { positions: { ...current.positions, ...mine }, version: current.version } }
          : old));
        void flush();
      } else {
        // Transient failure — keep the moves pending so the next flush retries them.
        for (const m of moves) if (!pending.current.has(m.motif_id)) pending.current.set(m.motif_id, { x: m.x, y: m.y });
      }
    }
  }, [bookId, token, qc, key]);

  /** Record a node's dropped position: optimistically reflect it, queue it, debounce the flush. */
  const savePosition = useCallback((motifId: string, x: number, y: number) => {
    pending.current.set(motifId, { x, y });
    qc.setQueryData<MotifGraphData>(key, (old) => (old
      ? { ...old, layout: { ...old.layout, positions: { ...old.layout.positions, [motifId]: { x, y } } } }
      : old));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), DEBOUNCE_MS);
  }, [flush, qc, key]);

  // Flush pending on tab-hide + unmount so a drag-then-close never loses a position.
  useEffect(() => {
    const onHide = () => { if (document.visibilityState === 'hidden') void flush(); };
    document.addEventListener('visibilitychange', onHide);
    return () => {
      document.removeEventListener('visibilitychange', onHide);
      if (timer.current) clearTimeout(timer.current);
      void flush();
    };
  }, [flush]);

  return {
    data: q.data, isLoading: q.isLoading, isError: q.isError, refetch: q.refetch, savePosition,
  };
}

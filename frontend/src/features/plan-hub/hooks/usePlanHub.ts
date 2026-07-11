// Plan Hub v2 (spec 24 §H2 / PH9) — the CONTROLLER. Produces the PlanHubView the canvas + panel
// consume. Cold open: getArcs + getPlanOverlay + getSceneLinks + getConformanceStatus fire in
// PARALLEL (four small reads) so the lane structure paints before any chapter window loads. Owns
// collapse state (which arcs/chapters are OPEN — default none open ⇒ every arc collapsed to a
// rollup, v1; camera-focus default is a later phase) + selectedId. Calls laneLayout ONCE — the
// single "where does a node go"; nothing here recomputes a position.
import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { getArcs, getConformanceStatus, getPlanOverlay, getSceneLinks } from '../api';
import { laneLayout } from '../layout/laneLayout';
import type { CollapseState, NodeContent, PlanHubView } from '../types';
import { usePlanWindows } from './usePlanWindows';
import { usePlanMoves } from './usePlanMoves';
import { useActualState } from './useActualState';
import { computeUnionState, toArcShellNode } from './planHubMappers';

export function usePlanHub(bookId: string): PlanHubView {
  const { accessToken } = useAuth();
  const token = accessToken ?? null;
  const enabled = !!token && !!bookId;

  // ── Cold-open reads (parallel). Shell is load-bearing; the three decorations are soft. ──
  const arcsQuery = useQuery({
    queryKey: ['plan-hub', 'arcs', bookId],
    queryFn: () => getArcs(bookId, token!),
    enabled,
  });
  const overlayQuery = useQuery({
    queryKey: ['plan-hub', 'overlay', bookId],
    queryFn: () => getPlanOverlay(bookId, token!),
    enabled,
    retry: false, // soft decoration — fail fast, render no problem badge
  });
  const sceneLinksQuery = useQuery({
    queryKey: ['plan-hub', 'scene-links', bookId],
    queryFn: () => getSceneLinks(bookId, token!),
    enabled,
    retry: false,
  });
  const conformanceQuery = useQuery({
    queryKey: ['plan-hub', 'conformance', bookId],
    queryFn: () => getConformanceStatus(bookId, token!),
    enabled,
    retry: false, // 404 until spec 26 ships ⇒ conformance=null (absent ≠ zero — no drift badge)
  });

  // Collapse is modelled as the OPENED sets (default empty ⇒ all collapsed, no shell seeding needed).
  const [expandedArcs, setExpandedArcs] = useState<Set<string>>(() => new Set());
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(() => new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const shell = useMemo(() => (arcsQuery.data?.arcs ?? []).map(toArcShellNode), [arcsQuery.data]);

  const expandedArcIds = useMemo(() => [...expandedArcs], [expandedArcs]);
  const expandedChapterIds = useMemo(() => [...expandedChapters], [expandedChapters]);

  // Only an OPEN arc/chapter loads its window; a collapsed arc's rollup comes from the shell.
  const windowsResult = usePlanWindows(bookId, token, expandedArcIds, expandedChapterIds);
  const actual = useActualState(bookId, token);

  // Translate the opened sets into laneLayout's CollapseState (which tracks the COLLAPSED ids).
  const collapse = useMemo<CollapseState>(() => {
    const collapsedArcs = shell.map((s) => s.id).filter((id) => !expandedArcs.has(id));
    const loadedChapterIds = windowsResult.windows.filter((w) => w.kind === 'chapter').map((w) => w.id);
    const collapsedChapters = loadedChapterIds.filter((id) => !expandedChapters.has(id));
    return { arcs: collapsedArcs, chapters: collapsedChapters };
  }, [shell, expandedArcs, expandedChapters, windowsResult.windows]);

  const layout = useMemo(
    () => laneLayout(shell, windowsResult.windows, collapse),
    [shell, windowsResult.windows, collapse],
  );

  const unionState = useMemo(() => {
    const sceneNodeIds = windowsResult.windows.filter((w) => w.kind === 'scene').map((w) => w.id);
    return computeUnionState(sceneNodeIds, actual.writtenNodeIds, actual.complete);
  }, [windowsResult.windows, actual.writtenNodeIds, actual.complete]);

  // Display scalars per node id: arc titles from the shell + chapter/scene titles from the loaded
  // windows (the window content wins on id collision — it never collides, arcs vs outline nodes).
  const nodeContent = useMemo<Record<string, NodeContent>>(() => {
    const out: Record<string, NodeContent> = {};
    for (const a of arcsQuery.data?.arcs ?? []) {
      out[a.id] = { title: a.title, status: a.status, kind: a.kind, tension: null, beatRole: null, chapterId: null };
    }
    for (const n of Object.values(windowsResult.content)) {
      out[n.id] = {
        title: n.title, status: n.status, kind: n.kind,
        tension: n.tension, beatRole: n.beat_role, chapterId: n.chapter_id,
      };
    }
    return out;
  }, [arcsQuery.data, windowsResult.content]);

  const toggleArc = useCallback((arcId: string) => {
    setExpandedArcs((prev) => {
      const next = new Set(prev);
      if (next.has(arcId)) next.delete(arcId);
      else next.add(arcId);
      return next;
    });
  }, []);

  const toggleChapter = useCallback((chapterId: string) => {
    setExpandedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(chapterId)) next.delete(chapterId);
      else next.add(chapterId);
      return next;
    });
  }, []);

  const select = useCallback((id: string | null) => setSelectedId(id), []);

  // ── H5 (PH20) writes — the three drag-to-move mutations live in usePlanMoves (which owns the
  // interaction rules: nest-vs-sibling, the OCC append position, the no-op guards). It needs BOTH
  // reload paths: the react-query invalidate for the shell, and windows.reload() for the hand-rolled
  // window slices — the rows a move actually mutates (invalidateQueries cannot reach those).
  const moves = usePlanMoves({
    bookId,
    token,
    shellNodes: arcsQuery.data?.arcs ?? [],
    windowContent: windowsResult.content,
    reloadWindows: windowsResult.reload,
    patchWindow: windowsResult.patch,
  });

  const loading = (enabled && arcsQuery.isLoading) || windowsResult.loading;
  const error =
    (arcsQuery.error instanceof Error ? arcsQuery.error.message : null) ?? windowsResult.error ?? null;

  return {
    layout,
    edges: sceneLinksQuery.data?.scene_links ?? [],
    overlay: overlayQuery.data ?? null,
    conformance: conformanceQuery.data ?? null,
    unionState,
    nodeContent,
    loading,
    error,
    selectedId,
    select,
    toggleArc,
    toggleChapter,
    moveChapterToArc: moves.moveChapterToArc,
    moveSceneToChapter: moves.moveSceneToChapter,
    moveArcTo: moves.moveArcTo,
    reorderChapter: moves.reorderChapter,
    moving: moves.moving,
    moveError: moves.moveError,
    undo: moves.undo,
  };
}

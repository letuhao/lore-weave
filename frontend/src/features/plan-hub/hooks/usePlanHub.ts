// Plan Hub v2 (spec 24 §H2 / PH9) — the CONTROLLER. Produces the PlanHubView the canvas + panel
// consume. Cold open: getArcs + getPlanOverlay + getSceneLinks + getConformanceStatus fire in
// PARALLEL (four small reads) so the lane structure paints before any chapter window loads. Owns
// collapse state (which arcs/chapters are OPEN — default none open ⇒ every arc collapsed to a
// rollup, v1; camera-focus default is a later phase) + selectedId. Calls laneLayout ONCE — the
// single "where does a node go"; nothing here recomputes a position.
import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  assignChapters, getArcs, getConformanceStatus, getPlanOverlay, getSceneLinks, reorderNode,
} from '../api';
import { laneLayout } from '../layout/laneLayout';
import type { CollapseState, NodeContent, PlanHubView } from '../types';
import { usePlanWindows } from './usePlanWindows';
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

  // ── H5 Row-1 (PH20): drag a chapter card into another lane → rebind its arc (structure_node_id).
  // The assign-chapters mirror is an idempotent bulk set (no OCC). On success invalidate every
  // plan-hub read for this book so the shell (chapter_count/span shift) + the windows + overlay
  // refetch and laneLayout re-places the card in its new lane. A refetch (not an optimistic patch)
  // keeps the source of truth server-side; the brief re-place is acceptable for v1 (optimistic is a
  // later polish). A failed move surfaces via moveChapterError; the card snaps back on the next render.
  const qc = useQueryClient();
  const moveMutation = useMutation({
    mutationFn: (vars: { chapterId: string; arcId: string }) =>
      assignChapters(bookId, vars.arcId, [vars.chapterId], token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plan-hub'] }),
  });
  const moveChapterToArc = useCallback(
    (chapterId: string, arcId: string) => {
      if (!token) return;
      moveMutation.mutate({ chapterId, arcId });
    },
    [token, moveMutation],
  );

  // ── H5 Row-4 (PH20): drag a scene card onto another chapter → re-parent it. Unlike the arc rebind
  // this IS a versioned node write, so it carries OCC: `If-Match: <version>` → a 412 means the scene
  // changed elsewhere. We invalidate on SETTLED (success OR error) so a conflict reloads the true
  // state — the SceneRail "changed elsewhere — reloaded" recovery, never a silent overwrite.
  const windowContent = windowsResult.content;
  const moveSceneMutation = useMutation({
    mutationFn: (vars: { sceneId: string; chapterId: string }) => {
      const scene = windowContent[vars.sceneId];
      if (!scene) throw new Error('scene not loaded');
      // Append AFTER the target chapter's last loaded scene. Byte-order rank compare matches the
      // server's fractional-rank collation (rank COLLATE "C"); no scenes loaded ⇒ first child.
      const siblings = Object.values(windowContent)
        .filter((n) => n.kind === 'scene' && n.parent_id === vars.chapterId && n.id !== vars.sceneId)
        .sort((a, b) => (a.rank < b.rank ? -1 : a.rank > b.rank ? 1 : a.id < b.id ? -1 : 1));
      const afterId = siblings.length ? siblings[siblings.length - 1].id : null;
      return reorderNode(
        vars.sceneId,
        { new_parent_id: vars.chapterId, after_id: afterId },
        scene.version,
        token!,
      );
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['plan-hub'] }),
  });
  const moveSceneToChapter = useCallback(
    (sceneId: string, chapterId: string) => {
      if (!token) return;
      const scene = windowContent[sceneId];
      // Unknown scene, or dropped back on its OWN chapter ⇒ no write (the canvas re-places it).
      if (!scene || scene.parent_id === chapterId) return;
      moveSceneMutation.mutate({ sceneId, chapterId });
    },
    [token, windowContent, moveSceneMutation],
  );

  // A failed move surfaces to the panel. A 412 is the OCC conflict: the reload already fired
  // (onSettled), so the message tells the user the canvas re-synced rather than lost their edit.
  const moveError = useMemo(() => {
    const e = (moveSceneMutation.error ?? moveMutation.error) as
      | (Error & { status?: number })
      | null;
    if (!e) return null;
    if (e.status === 412) return 'That node changed elsewhere — the canvas reloaded. Try the move again.';
    return e.message || 'Move failed.';
  }, [moveSceneMutation.error, moveMutation.error]);

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
    moveChapterToArc,
    moveSceneToChapter,
    moving: moveMutation.isPending || moveSceneMutation.isPending,
    moveError,
  };
}

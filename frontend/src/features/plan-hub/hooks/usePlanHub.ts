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
import type { ArcPagination, CollapseState, NodeContent, PlanHubView } from '../types';
import { usePlanWindows } from './usePlanWindows';
import { usePlanMoves } from './usePlanMoves';
import { useActualState } from './useActualState';
import { useExtractPlan } from './useExtractPlan';
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
    // 26 IX-14 HAS shipped (`arc_conformance_state` is live), so this normally resolves. It can
    // still legitimately answer "nothing computed" — an arc that has never had a conformance run
    // arrives `computed_at: null, dirty: true` and renders as such. A FAILED read ⇒ conformance=null
    // ⇒ no drift badge at all: absent ≠ zero, never a green-looking 0.
    retry: false,
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

  // OQ-5 — open every ANCESTOR of an arc so the arc itself becomes a rendered node.
  // An arc renders as a rollup card only when it is the OUTERMOST collapsed one: under a collapsed
  // ancestor it is suppressed entirely (folded into that ancestor's rollup). So in the default
  // all-collapsed view, a rail click on any nested arc had nothing to pan TO — the camera no-op'd and
  // the row just highlighted. Opening the ancestors is what makes the target exist.
  const expandAncestorsOf = useCallback(
    (nodeId: string) => {
      const byId = new Map(shell.map((n) => [n.id, n]));
      const ancestors: string[] = [];
      for (let p = byId.get(nodeId)?.parent_id ?? null, hops = 0; p && hops < 8; hops++) {
        ancestors.push(p);
        p = byId.get(p)?.parent_id ?? null;
      }
      if (!ancestors.length) return;
      setExpandedArcs((prev) => {
        if (ancestors.every((a) => prev.has(a))) return prev; // already open — keep the identity
        return new Set([...prev, ...ancestors]);
      });
    },
    [shell],
  );

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

  // PH11 — per-arc window state for the lane header. `total` is the arc's TRUE `chapter_count` from
  // the shell, never the loaded length: the two differing is exactly what tells the user (and the
  // "+ more" button) that chapters 101..340 exist but aren't on screen. `loadMoreArc` was exported
  // by usePlanWindows and consumed by NOBODY, so those chapters were unreachable — invisible on the
  // canvas and therefore impossible to drag, with nothing admitting they were there.
  const arcPagination = useMemo(() => {
    const loadedByArc: Record<string, number> = {};
    for (const w of windowsResult.windows) {
      if (w.kind !== 'chapter' || !w.structure_node_id) continue;
      loadedByArc[w.structure_node_id] = (loadedByArc[w.structure_node_id] ?? 0) + 1;
    }
    const out: Record<string, ArcPagination> = {};
    for (const a of arcsQuery.data?.arcs ?? []) {
      out[a.id] = {
        loaded: loadedByArc[a.id] ?? 0,
        total: a.chapter_count,
        hasMore: !!windowsResult.arcHasMore[a.id],
        loading: !!windowsResult.arcLoading[a.id],
      };
    }
    return out;
  }, [arcsQuery.data, windowsResult.windows, windowsResult.arcHasMore, windowsResult.arcLoading]);

  // PH21 CTA — the decompiler. Lives here (not in the panel) so the panel stays a view.
  const extract = useExtractPlan(bookId, token, windowsResult.reload);

  const loading = (enabled && arcsQuery.isLoading) || windowsResult.loading;
  const error =
    (arcsQuery.error instanceof Error ? arcsQuery.error.message : null) ?? windowsResult.error ?? null;

  // PH21 — "this book has no spec at all". Both halves must have ANSWERED, not merely be absent:
  //   • the arc shell resolved with zero arcs, AND
  //   • the unassigned window resolved with zero chapters (with no arcs, that is the ONLY window
  //     that can hold a chapter node — nothing else is loadable).
  // Gating on `isSuccess` (not `!data`) is what keeps this from flashing the empty state — and,
  // worse, offering to EXTRACT a plan — over a book whose reads simply haven't landed yet.
  const specEmpty =
    arcsQuery.isSuccess &&
    shell.length === 0 &&
    windowsResult.unassignedLoaded &&
    layout.unassigned.length === 0;

  // PH21 tray. `undefined` on the wire ⇒ the coverage diff could not be computed (book-service
  // unreadable) ⇒ null here ⇒ the tray renders "unknown", never an empty (green-looking) tray.
  const overlay = overlayQuery.data ?? null;
  const unplanned = overlay?.unplanned_chapters ?? null;

  // ── Degradation notices — every partial truth the Hub is currently rendering, in ONE place ──
  //
  // The Hub degrades gracefully in several ways, and every one of them used to be SILENT: the canvas
  // simply showed less, and looked exactly like a healthy canvas showing less. That is the reader's
  // side of `silent-success-is-a-bug`. Each of these is computed somewhere already; the bug was that
  // nobody rendered it.
  const notices = useMemo(() => {
    const out: string[] = [];
    // The two-truths join is DEAD. Without it `complete` stays false, computeUnionState emits no
    // verdicts, and every card renders neutral — a fully-written book looks entirely unwritten.
    if (actual.error) {
      out.push(
        `The manuscript could not be read, so "written vs not yet written" is not shown (${actual.error}).`,
      );
    }
    // The overlay capped its refs (OUT-5). Counts stay exact, so a badge can read "3" while the
    // drawer lists 1 — say why rather than letting it look like a bug.
    if (overlay?.problems.refs_capped) {
      out.push('Too many canon/thread references to list them all — counts are exact, the lists are truncated.');
    }
    // Anything the server itself flagged (today: the coverage diff could not be computed).
    for (const w of overlay?.warnings ?? []) out.push(w);
    return out;
  }, [actual.error, overlay]);

  return {
    layout,
    edges: sceneLinksQuery.data?.scene_links ?? [],
    overlay,
    conformance: conformanceQuery.data ?? null,
    unionState,
    nodeContent,
    specEmpty,
    unplanned,
    unplannedCount: overlay?.unplanned_count ?? unplanned?.length ?? 0,
    arcPagination,
    loadMoreArc: windowsResult.loadMoreArc,
    linkScenes: moves.linkScenes,
    unlinkScenes: moves.unlinkScenes,
    extract,
    notices,
    loading,
    error,
    selectedId,
    select,
    toggleArc,
    toggleChapter,
    expandAncestorsOf,
    moveChapterToArc: moves.moveChapterToArc,
    moveSceneToChapter: moves.moveSceneToChapter,
    moveArcTo: moves.moveArcTo,
    reorderChapter: moves.reorderChapter,
    moving: moves.moving,
    moveError: moves.moveError,
    undo: moves.undo,
  };
}

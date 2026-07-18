// Plan Hub v2 (spec 24 §H2 / PH9) — the CONTROLLER. Produces the PlanHubView the canvas + panel
// consume. Cold open: getArcs + getPlanOverlay + getSceneLinks + getConformanceStatus fire in
// PARALLEL (four small reads) so the lane structure paints before any chapter window loads. Owns
// collapse state (which arcs/chapters are OPEN — default none open ⇒ every arc collapsed to a
// rollup, v1; camera-focus default is a later phase) + selectedId. Calls laneLayout ONCE — the
// single "where does a node go"; nothing here recomputes a position.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { getArcs, getConformanceStatus, getPlanOverlay, getSceneLinks } from '../api';
import { laneLayout } from '../layout/laneLayout';
import type { ArcListNode } from '../types';

/** How many root arcs Advanced opens on first show. Bounds the cold-open cost (each opened arc fires
 *  ONE chapter-window fetch, after paint) so a 1000-arc book never fetches 1000 windows at once, while
 *  a normal book shows its whole hierarchy by default (mockup "root fix 2") instead of a wall of
 *  collapsed rollups. */
const MAX_AUTO_EXPAND = 8;

/** The first N ROOT arc ids (rank order) — the bounded set Advanced auto-expands. Roots only: a
 *  sub-arc opens with its parent. */
function autoExpandArcIds(arcs: ArcListNode[], max: number): string[] {
  const byId = new Map(arcs.map((a) => [a.id, a]));
  return arcs
    .filter((a) => !a.parent_id || !byId.has(a.parent_id))
    .slice()
    .sort((a, b) => (a.rank < b.rank ? -1 : a.rank > b.rank ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .slice(0, max)
    .map((a) => a.id);
}
import type {
  ArcPagination,
  CollapseState,
  NodeContent,
  PlanHubView,
  UnplannedChapter,
} from '../types';
import { normalizeSource } from '../types';
import { usePlanWindows } from './usePlanWindows';
import { usePlanMoves } from './usePlanMoves';
import { useExtractPlan } from './useExtractPlan';
import { useEntityNames } from './useEntityNames';
import { usePlanNodeWrites } from './usePlanNodeWrites';
import { useBookChapters } from './useBookChapters';
import { computeUnionState, toArcShellNode } from './planHubMappers';

export function usePlanHub(
  bookId: string,
  opts: { autoExpandArcs?: boolean } = {},
): PlanHubView {
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
  // Allow bounded auto-expand to re-seed for a NEW book (cleared alongside the sets on book change).
  const seededBook = useRef<string | null>(null);

  // Reset per-book view state when the studio switches books IN PLACE (the panel is not always
  // remounted — `usePlanWindows` resets its own slices on `bookId` for the same reason). Without this,
  // book A's expanded arcs + selection LEAK into book B: `usePlanWindows` then fetches book A's arc ids
  // against book B (wasted, and an error flips the whole panel to its error branch), and the always-
  // mounted drawer holds a node id that doesn't exist in book B. Declared BEFORE the auto-expand effect
  // so, on a book change, it clears `seededBook` first and the new book re-seeds cleanly.
  useEffect(() => {
    setExpandedArcs(new Set());
    setExpandedChapters(new Set());
    setSelectedId(null);
    seededBook.current = null;
  }, [bookId]);

  const shell = useMemo(() => (arcsQuery.data?.arcs ?? []).map(toArcShellNode), [arcsQuery.data]);

  const expandedArcIds = useMemo(() => [...expandedArcs], [expandedArcs]);
  const expandedChapterIds = useMemo(() => [...expandedChapters], [expandedChapters]);

  // Only an OPEN arc/chapter loads its window; a collapsed arc's rollup comes from the shell.
  const windowsResult = usePlanWindows(bookId, token, expandedArcIds, expandedChapterIds);

  // SC11 amendment — THE MANUSCRIPT READ IS GONE. `useActualState` paged book-service's scene index
  // per loaded chapter to derive "written vs not yet written"; that fact now rides the node payload
  // itself (`written`, maintained server-side). One fewer read, and PH9's ≤5-request cold-open budget
  // gains headroom rather than spending it.
  // Read surface #6 (PH26) — the book-wide entity-names map behind the cast chips. One cached load;
  // it is one of the five cold-open reads the PH9 budget already accounts for.
  const entityNames = useEntityNames(bookId);

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


  const unionState = useMemo(
    () =>
      computeUnionState(
        windowsResult.windows
          .filter((w) => w.kind === 'scene')
          .map((w) => ({ id: w.id, written: w.written })),
      ),
    [windowsResult.windows],
  );

  // Display scalars per node id: arc titles from the shell + chapter/scene titles from the loaded
  // windows (the window content wins on id collision — it never collides, arcs vs outline nodes).
  const nodeContent = useMemo<Record<string, NodeContent>>(() => {
    const out: Record<string, NodeContent> = {};
    for (const a of arcsQuery.data?.arcs ?? []) {
      out[a.id] = {
        title: a.title, status: a.status, kind: a.kind, tension: null, beatRole: null,
        chapterId: null, castIds: [], castCount: 0,
        // AUTHORSHIP (redesign) — normalise the wire enum to the 2-value FE coding (non-'authored' ⇒ AI).
        source: normalizeSource(a.source),
      };
    }
    for (const n of Object.values(windowsResult.content)) {
      out[n.id] = {
        title: n.title, status: n.status, kind: n.kind,
        tension: n.tension, beatRole: n.beat_role, chapterId: n.chapter_id,
        // PH26 — the cast the server already capped to 3, plus the EXACT count for the +N chip.
        castIds: n.present_entity_ids ?? [],
        castCount: n.present_entity_count ?? 0,
        // AUTHORSHIP (redesign) — normalise the wire enum to the 2-value FE coding (non-'authored' ⇒ AI).
        source: normalizeSource(n.source),
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

  // Idempotent bulk-open (the flow view's bounded auto-expand). Adds only — never collapses an arc
  // the user has since closed, and keeps the set's identity when every id is already open (no
  // needless re-render / re-fetch). Distinct from toggleArc, which flips one id.
  const expandArcs = useCallback((arcIds: string[]) => {
    setExpandedArcs((prev) => {
      if (arcIds.every((id) => prev.has(id))) return prev;
      return new Set([...prev, ...arcIds]);
    });
  }, []);

  // Bounded auto-expand for the lane-flow view (mockup "root fix 2": show the hierarchy by default).
  // Seeds ONCE per book, only when the caller asks (Advanced mode) — so Simple mode never fires a
  // chapter-window fetch — and only the first MAX_AUTO_EXPAND roots, so a huge book stays bounded.
  // Seeding once (the `seededBook` ref, cleared on book change above) means a user who then COLLAPSES
  // an auto-opened arc keeps it closed.
  useEffect(() => {
    if (!opts.autoExpandArcs || !arcsQuery.isSuccess) return;
    if (seededBook.current === bookId) return;
    seededBook.current = bookId;
    const roots = autoExpandArcIds(arcsQuery.data?.arcs ?? [], MAX_AUTO_EXPAND);
    if (roots.length) expandArcs(roots);
  }, [opts.autoExpandArcs, arcsQuery.isSuccess, arcsQuery.data, bookId, expandArcs]);

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

  // PH20 — the drawer's writes + the chapter spine the ⚓ re-anchor picker needs (BPS-13). The spine
  // walk is gated on a SELECTION: it is a drawer control, and firing it on mount was a ~100-request
  // cold-open violation (see useBookChapters' header).
  const nodeWrites = usePlanNodeWrites(bookId, token, windowsResult.reload);
  const chapterSpine = useBookChapters(bookId, token, selectedId !== null);

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

  // PH21 tray — THREE states, not two. `overlay` is null while the query is still in flight AND
  // when it degraded, and collapsing those would flash "the manuscript could not be read" on every
  // cold open (the overlay is the slowest of the parallel reads). The absent≠zero law, broken in
  // the other direction: absent ≠ degraded.
  //   undefined ⇒ still loading — the tray renders nothing
  //   null      ⇒ the server ANSWERED and omitted the key — the tray says "unknown"
  //   []        ⇒ nothing is unplanned
  const overlay = overlayQuery.data ?? null;
  const unplanned: UnplannedChapter[] | null | undefined = overlayQuery.isPending
    ? undefined
    : (overlay?.unplanned_chapters ?? null);

  // The book-wide problem total. It MUST come from the exact per-node counts, never from the refs
  // list: the server caps refs at 50 globally while keeping counts exact (the OUT-5 split), so
  // summing `refs.length` would silently report "50" for a book with 300 problems. Sum LEAF entries
  // only — `by_node` also carries arc-subtree rollups, and adding those would double-count.
  const problemTotal = useMemo(() => {
    const by = overlay?.problems.by_node ?? {};
    const arcIds = new Set((arcsQuery.data?.arcs ?? []).map((a) => a.id));
    return Object.entries(by)
      .filter(([id]) => !arcIds.has(id)) // drop the rollup entries; keep the leaves
      .reduce((n, [, p]) => n + p.canon + p.threads_open, 0);
  }, [overlay, arcsQuery.data]);

  // ── Degradation notices — every partial truth the Hub is currently rendering, in ONE place ──
  //
  // The Hub degrades gracefully in several ways, and every one of them used to be SILENT: the canvas
  // simply showed less, and looked exactly like a healthy canvas showing less. That is the reader's
  // side of `silent-success-is-a-bug`. Each of these is computed somewhere already; the bug was that
  // nobody rendered it.
  const notices = useMemo(() => {
    const out: string[] = [];
    // (The old "the manuscript could not be read" notice is GONE with `useActualState`. There is no
    // separate manuscript read left to fail: `written` rides the node payload, so if the nodes
    // loaded, the verdict loaded with them — and if they did not, the canvas is empty anyway. One
    // fewer degradation mode, because one fewer read.)
    // The overlay capped its refs (OUT-5). Counts stay exact, so a badge can read "3" while the
    // drawer lists 1 — say why rather than letting it look like a bug.
    if (overlay?.problems.refs_capped) {
      out.push('Too many canon/thread references to list them all — counts are exact, the lists are truncated.');
    }
    // Anything the server itself flagged (today: the coverage diff could not be computed).
    for (const w of overlay?.warnings ?? []) out.push(w);
    return out;
  }, [overlay]);

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
    problemTotal,
    arcPagination,
    loadMoreArc: windowsResult.loadMoreArc,
    linkScenes: moves.linkScenes,
    unlinkScenes: moves.unlinkScenes,
    resolveEntity: entityNames.resolve,
    nodeWrites,
    chapters: chapterSpine.chapters,
    chaptersError: chapterSpine.error,
    extract,
    notices,
    loading,
    error,
    selectedId,
    select,
    toggleArc,
    expandArcs,
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

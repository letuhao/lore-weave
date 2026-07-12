// 24 Plan Hub v2 (H2.1 + H3 + H2.6 bus/camera) — the `plan-hub` dock panel: the whole package on the
// graph canvas. TOOLBAR (PH15) · graph CANVAS (React Flow, positions from the pure laneLayout —
// PH14) · right DETAIL DRAWER (H3, over the canvas) · the PH21 unplanned tray docked beneath.
//
// The Plan NAVIGATOR is deliberately NOT in here. PH25 puts it in the ACTIVITY BAR (it and the canvas
// are two densities of one dataset), and OQ-6 ✅ rejects a third in-panel list as a duplicate of it.
// It reaches us over the studio bus (`planFocusNode`) — it lives outside the dock and cannot hand us
// a callback.
//
// Logic lives in usePlanHub (the controller producing PlanHubView); this file wires it to the
// regions, subscribes the bus, and self-registers as a studio panel. Book-scoped.
//
// Selection is ONE piece of state (view.selectedId) shared across all three: a canvas node click, a
// rail row click (onFocusNode), and the drawer all read/write it. A rail/canvas selection whose kind
// is arc/saga resolves against the SAME shell the rail draws (rollup node id === structure_node id,
// laneLayout); a chapter/scene resolves via the drawer's per-node fetch.
//
// H2.6 bus: subscribe the editor's active-chapter signal (focusManuscriptUnit publishes it — verified
// in StudioHostProvider) → a "you are here" highlight on the node whose chapterId matches. OQ-5 camera:
// a rail focus pans the canvas to the node (focusNode = select + bump the focus seq). The reverse
// publish (planHub.selection) is deferred — no consumer reads a Hub-selection bus slice yet.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioBusSelector, useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { usePlanHub } from '@/features/plan-hub/hooks/usePlanHub';
import type { CameraFocusTarget, PlanOverlayRef } from '@/features/plan-hub/types';
import {
  PlanCanvas,
  PlanDrawer,
  PlanEmptyState,
  PlanToolbar,
  UnplannedTray,
} from '@/features/plan-hub/components';
import type { PlanViewMode } from '@/features/plan-hub/components/PlanToolbar';

export function PlanHubPanel(props: IDockviewPanelProps) {
  useStudioPanel('plan-hub', props.api);
  const { t } = useTranslation('studio');
  const { bookId, openPanel, focusManuscriptUnit } = useStudioHost();
  const view = usePlanHub(bookId);

  // H2.6 — the editor's active chapter (book-service chapter_id) off the bus. Map it to the Hub node
  // whose loaded content carries that chapterId; null when nothing's open or its window isn't loaded.
  const activeChapterId = useStudioBusSelector((s) => s.activeChapterId);
  const activeNodeId = useMemo(() => {
    if (!activeChapterId) return null;
    // Match the CHAPTER node only — the editor's active unit is a chapter, and only chapter nodes
    // carry a chapter_id (scenes' is null); the kind guard also immunises against any scene-side
    // denormalisation of chapter_id from picking a scene over its chapter.
    const hit = Object.entries(view.nodeContent).find(
      ([, c]) => c.kind === 'chapter' && c.chapterId === activeChapterId,
    );
    return hit ? hit[0] : null;
  }, [activeChapterId, view.nodeContent]);

  // PH18 deep-links — a problem ref opens its OWNING lens, FOCUSED on the offending row. Routed
  // through openPanel, never navigate() (PH24/DOCK-7).
  //   canon  → focus the RULE (`canon_rule.id`), which the panel's critic lane keys on, PLUS the
  //            node's chapter, which its entity-continuity lane keys on. The two lanes answer
  //            different questions and neither id alone reaches both.
  //   thread → focus the THREAD id directly (narrative_thread.id IS what the promises panel lists)
  // Recorded in RUN-STATE §6 as D-04 (PO approved option B: surface the rule-keyed lane).
  const openRef = useCallback(
    (ref: PlanOverlayRef, nodeId: string) => {
      if (ref.kind === 'thread') {
        openPanel('quality-promises', { focus: true, params: { bookId, focusThreadId: ref.id } });
        return;
      }
      const chapterId = view.nodeContent[nodeId]?.chapterId ?? null;
      openPanel('quality-canon', {
        focus: true,
        params: { bookId, focusRuleId: ref.id, focusChapterId: chapterId },
      });
    },
    [openPanel, bookId, view.nodeContent],
  );

  // ── PH15 toolbar state ──────────────────────────────────────────────────────────────────────
  const [search, setSearch] = useState('');
  const [fitSignal, setFitSignal] = useState(0);
  // PH22 ✅ P-10: v1 is narrative-only. The state exists (and the other two buttons are visible +
  // disabled) so the mode is a real, discoverable concept rather than a silently absent one.
  const [viewMode, setViewMode] = useState<PlanViewMode>('narrative');

  // A FIND, not a filter: matched nodes are ringed and everything stays exactly where it was.
  // Filtering would re-lay the canvas out under the user, which PH14 forbids ("an insert must shift,
  // never reshuffle"). Empty query ⇒ undefined ⇒ the cards render no find state at all.
  const matchedIds = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return undefined;
    const hits = new Set<string>();
    for (const [id, c] of Object.entries(view.nodeContent)) {
      if (c.title?.toLowerCase().includes(q)) hits.add(id);
    }
    return hits;
  }, [search, view.nodeContent]);

  // OQ-5 camera — a focus REQUEST (nodeId + monotonically bumped seq so re-focusing the same node
  // still pans). A rail row focus selects AND pans; a canvas click only selects (already in view).
  const [focusTarget, setFocusTarget] = useState<CameraFocusTarget | null>(null);
  const { select, expandAncestorsOf } = view;
  const focusNode = useCallback(
    (nodeId: string) => {
      // Open the ancestors FIRST: a nested arc under a collapsed one isn't drawn, so the camera
      // would have nothing to pan to. The pan itself fires as soon as the node appears (the camera
      // waits for it rather than giving up on the frame the request was made).
      expandAncestorsOf(nodeId);
      setFocusTarget((prev) => ({ nodeId, seq: (prev?.seq ?? 0) + 1 }));
      select(nodeId);
    },
    [select, expandAncestorsOf],
  );

  // PH25 — the ACTIVITY BAR's Plan rail lives outside the dock, so it asks over the bus rather than
  // handing us a callback. We diff the seq (not the nodeId) so re-clicking the SAME row still pans,
  // and a fresh mount never replays a stale request. This is a legitimate useEffect: it synchronises
  // an external request stream onto our imperative camera, not a reaction to our own state.
  const planFocus = useStudioBusSelector((s) => s.planFocusSeq);
  const planFocusNodeId = useStudioBusSelector((s) => s.planFocusNodeId);
  const lastPlanFocus = useRef<number | undefined>(planFocus);
  useEffect(() => {
    if (planFocus === undefined || planFocus === lastPlanFocus.current) return;
    lastPlanFocus.current = planFocus;
    if (planFocusNodeId) focusNode(planFocusNodeId);
  }, [planFocus, planFocusNodeId, focusNode]);

  if (view.error) {
    return (
      <div
        data-testid="studio-plan-hub-panel"
        className="flex h-full w-full items-center justify-center p-4 text-sm text-destructive"
      >
        {view.error}
      </div>
    );
  }

  // Cold open — the shell has not landed yet. Without this the Hub rendered an EMPTY CANVAS while
  // loading, which is indistinguishable from a book with no plan: the user sees "nothing here" and
  // has no idea whether that is the answer or the question. (Ordered before `specEmpty` on purpose —
  // "still loading" must win over "nothing found".)
  if (view.loading && view.layout.lanes.length === 0 && view.layout.nodes.length === 0) {
    return (
      <div
        data-testid="studio-plan-hub-panel"
        className="flex h-full w-full items-center justify-center p-4 text-sm text-muted-foreground"
      >
        <span data-testid="plan-hub-loading">{t('planHub.loading', 'Loading the plan…')}</span>
      </div>
    );
  }

  // PH21 — the book has no spec at all. Offer the two honest verbs (extract / plan) instead of a
  // blank canvas. `specEmpty` is false until BOTH reads have answered, so this never flashes over a
  // book whose plan simply hasn't loaded (absent ≠ empty). "Plan from scratch" opens the PlanForge
  // panel via the host — zero navigate() (PH24/DOCK-7).
  if (view.specEmpty) {
    return (
      <div data-testid="studio-plan-hub-panel" className="h-full w-full">
        <PlanEmptyState
          onExtract={view.extract.run}
          onPlanFromScratch={() => openPanel('planner', { focus: true })}
          extracting={view.extract.extracting}
          result={view.extract.result}
          error={view.extract.error}
        />
      </div>
    );
  }

  // The selected node's kind routes the drawer's facet set + which backend it reads (arc/saga from
  // the shell, chapter/scene via getNode). nodeContent is keyed by node id for every drawn node.
  const selectedKind = view.selectedId ? view.nodeContent[view.selectedId]?.kind ?? null : null;

  return (
    <div data-testid="studio-plan-hub-panel" className="flex h-full w-full min-h-0">
      {/* PH25/OQ-6 — the Plan navigator is NOT a column in here. It is an ACTIVITY BAR rail (it and
          the canvas are two densities of one dataset), and OQ-6 rejects a third in-panel list as a
          duplicate of it. It reaches us over the bus (`planFocusNode`, subscribed above). */}
      {/* center column: TOOLBAR + graph + the H3 drawer overlay, with the PH21 tray docked beneath.
          The canvas gets `relative` so the drawer's `absolute right-0` pins to THAT region and not
          the window (the dockview fixed-positioning bug); the toolbar and tray sit OUTSIDE it, in
          normal flow, so neither overlaps the drawer. */}
      <div className="flex min-w-0 flex-1 flex-col">
      <PlanToolbar
        search={search}
        onSearch={setSearch}
        onFit={() => setFitSignal((n) => n + 1)}
        onProblems={() => openPanel('quality', { focus: true, params: { bookId } })}
        // OQ-7 ✅ P-13: "Ask AI" is NOT a canvas-native plan agent — it is the Compose chat, opened
        // with the current selection as its subject. Null with nothing selected: there'd be no
        // subject to ask ABOUT, and the button says so rather than opening an empty chat.
        onAskAi={
          view.selectedId
            ? () =>
                openPanel('compose', {
                  focus: true,
                  params: { bookId, subjectNodeId: view.selectedId },
                })
            : null
        }
        view={viewMode}
        onView={setViewMode}
        problemCount={view.problemTotal}
      />
      <div className="relative min-w-0 flex-1">
        <PlanCanvas
          layout={view.layout}
          edges={view.edges}
          overlay={view.overlay}
          conformance={view.conformance}
          unionState={view.unionState}
          nodeContent={view.nodeContent}
          selectedId={view.selectedId}
          onSelect={view.select}
          onToggleArc={view.toggleArc}
          onToggleChapter={view.toggleChapter}
          activeNodeId={activeNodeId}
          focusTarget={focusTarget}
          onMoveChapter={view.moveChapterToArc}
          onMoveScene={view.moveSceneToChapter}
          onMoveArc={view.moveArcTo}
          onReorderChapter={view.reorderChapter}
          arcPagination={view.arcPagination}
          onLoadMoreArc={view.loadMoreArc}
          onOpenRef={openRef}
          onLinkScenes={view.linkScenes}
          onUnlinkScenes={view.unlinkScenes}
          resolveEntity={view.resolveEntity}
          fitSignal={fitSignal}
          matchedIds={matchedIds}
          busy={view.moving}
        />
        {/* PH21 — a HUD notice for the UNASSIGNED strip (spec chapters bound to no arc — the normal
            post-decompile state). Their cards render in a strip below the lanes and drag into a lane
            through the ordinary Row-1 path; this just says how many there are, since the strip can
            be scrolled out of view on a tall canvas. NOT the unplanned tray — that is the other
            direction (manuscript chapters with no spec node) and docks below. */}
        {view.layout.unassigned.length > 0 && (
          <div
            data-testid="plan-hub-unassigned-notice"
            className="pointer-events-none absolute left-3 top-3 z-20 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs text-amber-700 shadow"
          >
            {t('planHub.node.unassignedStrip', {
              count: view.layout.unassigned.length,
              defaultValue: '{{count}} chapter in no arc — drag it into a lane',
              defaultValue_other: '{{count}} chapters in no arc — drag them into a lane',
            })}
          </div>
        )}
        {/* A failed move (incl. the 412 "changed elsewhere — reloaded" OCC recovery) is surfaced,
            never swallowed — the canvas has already re-synced from the server underneath it. */}
        {view.moveError && (
          <div
            data-testid="plan-hub-move-error"
            className="pointer-events-none absolute bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-1.5 text-xs text-destructive shadow"
          >
            {view.moveError}
          </div>
        )}
        {/* One-level UNDO of the last successful move. It matters most for Row-3, which mutates the
            actual manuscript order — a mis-aimed drag should be one click to reverse, not a hunt
            through the chapter list. Hidden while a move is in flight (the inverse would be aimed at
            a layout the server is about to replace). */}
        {view.undo && !view.moveError && !view.moving && (
          <div className="absolute bottom-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-md border bg-background/95 px-3 py-1.5 text-xs shadow">
            <span className="text-muted-foreground">{view.undo.label}</span>
            <button
              type="button"
              data-testid="plan-hub-undo"
              className="font-medium text-primary underline-offset-2 hover:underline"
              onClick={() => view.undo?.run()}
            >
              {t('planHub.undo', 'Undo')}
            </button>
          </div>
        )}
        {/* Always mounted — PlanDrawer self-hides on a null selection (never conditionally unmount a
            stateful child). onClose clears the selection, which also drops the rail/canvas highlight. */}
        <PlanDrawer
          selectedId={view.selectedId}
          kind={selectedKind}
          bookId={bookId}
          onClose={() => view.select(null)}
          overlay={view.overlay}
          onOpenRef={openRef}
          writes={view.nodeWrites}
          chapters={view.chapters}
          onOpenInEditor={(chapterId) => focusManuscriptUnit(chapterId)}
        />
      </div>

        {/* Every partial truth the canvas is currently showing, said out loud. The Hub degrades in
            several ways (the manuscript join dead ⇒ no written/not-written treatment; refs capped;
            the coverage diff uncomputable) and each used to degrade SILENTLY — showing less, and
            looking exactly like a healthy canvas showing less. */}
        {view.notices.length > 0 && (
          <ul
            data-testid="plan-hub-notices"
            className="border-t border-amber-500/30 bg-amber-500/5 px-3 py-1 text-xs text-amber-700"
          >
            {view.notices.map((n) => (
              <li key={n} data-testid="plan-hub-notice">
                {n}
              </li>
            ))}
          </ul>
        )}

        {/* PH21 — manuscript chapters no spec node covers. Drift made visible, never auto-planned.
            Self-hides when there are none AND we know it; renders "unknown" when the coverage diff
            could not be computed. A row opens the chapter in the EDITOR — the unplanned chapter has
            no spec node to select, so the only truthful destination is where it actually lives. */}
        <UnplannedTray
          chapters={view.unplanned}
          total={view.unplannedCount}
          onOpenChapter={(chapterId) => focusManuscriptUnit(chapterId)}
        />
      </div>
    </div>
  );
}

// 24 Plan Hub v2 (H2.1 + H3/H6 integrate + H2.6 bus/camera) — the `plan-hub` dock panel: the whole
// package on the graph canvas. Left NAVIGATOR RAIL (H6, the list rendering of the same arc shell) ·
// center graph CANVAS (React Flow, positions from the pure laneLayout — PH14) · right DETAIL DRAWER
// (H3, opens over the canvas for the selected node). Logic lives in usePlanHub (the controller
// producing PlanHubView); this file wires the controller to the three regions, subscribes the studio
// bus, and self-registers/titles as a studio panel. Book-scoped (bookId from the studio host).
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
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioBusSelector, useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { usePlanHub } from '@/features/plan-hub/hooks/usePlanHub';
import type { CameraFocusTarget } from '@/features/plan-hub/types';
import { PlanCanvas, PlanDrawer, PlanNavigatorRail } from '@/features/plan-hub/components';

export function PlanHubPanel(props: IDockviewPanelProps) {
  useStudioPanel('plan-hub', props.api);
  const { t } = useTranslation('studio');
  const { bookId } = useStudioHost();
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

  // The selected node's kind routes the drawer's facet set + which backend it reads (arc/saga from
  // the shell, chapter/scene via getNode). nodeContent is keyed by node id for every drawn node.
  const selectedKind = view.selectedId ? view.nodeContent[view.selectedId]?.kind ?? null : null;

  return (
    <div data-testid="studio-plan-hub-panel" className="flex h-full w-full min-h-0">
      {/* H6 — left navigator rail (the same arc shell, react-query DEDUPES the getArcs call). A row
          click focuses the node on the canvas (pan) — never opens the editor (PH25). */}
      <div className="flex w-48 min-w-0 flex-shrink-0 flex-col border-r bg-muted/20">
        <PlanNavigatorRail bookId={bookId} onFocusNode={focusNode} selectedId={view.selectedId} />
      </div>

      {/* center graph + the H3 drawer overlay. `relative` so the drawer's `absolute right-0` pins to
          THIS region, not the window (dockview-panel-fixed-positioning bug). */}
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
          busy={view.moving}
        />
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
        />
      </div>
    </div>
  );
}

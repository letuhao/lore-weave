// 24 Plan Hub v2 (H2.1 + H3/H6 integrate) — the `plan-hub` dock panel: the whole package on the
// graph canvas. Left NAVIGATOR RAIL (H6, the list rendering of the same arc shell) · center graph
// CANVAS (React Flow, positions from the pure laneLayout — PH14) · right DETAIL DRAWER (H3, opens
// over the canvas for the selected node). Logic lives in usePlanHub (the controller producing
// PlanHubView); this file only wires the controller to the three regions and self-registers/titles
// as a studio panel. Book-scoped (bookId from the studio host).
//
// Selection is ONE piece of state (view.selectedId) shared across all three: a canvas node click, a
// rail row click (onFocusNode), and the drawer all read/write it. A rail/canvas selection whose kind
// is arc/saga resolves against the SAME shell the rail draws (rollup node id === structure_node id,
// laneLayout); a chapter/scene resolves via the drawer's per-node fetch. Camera-pan to a focused node
// is a later phase (OQ-5) — for now onFocusNode selects+opens the drawer without panning.
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { usePlanHub } from '@/features/plan-hub/hooks/usePlanHub';
import { PlanCanvas, PlanDrawer, PlanNavigatorRail } from '@/features/plan-hub/components';

export function PlanHubPanel(props: IDockviewPanelProps) {
  useStudioPanel('plan-hub', props.api);
  const { bookId } = useStudioHost();
  const view = usePlanHub(bookId);

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
      {/* H6 — left navigator rail (the same arc shell, react-query DEDUPES the getArcs call). */}
      <div className="flex w-48 min-w-0 flex-shrink-0 flex-col border-r bg-muted/20">
        <PlanNavigatorRail bookId={bookId} onFocusNode={view.select} selectedId={view.selectedId} />
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
        />
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

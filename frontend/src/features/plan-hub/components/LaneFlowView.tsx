// Plan Hub redesign — the ADVANCED view, rebuilt to the sealed mockup
// (`design-drafts/plan-hub-redesign/index.html`). A dotted-grid CANVAS holding vertically-stacked arc
// LANES (FlowLane), each with wrapping chapter cards + inset sub-arcs. This REPLACES the React Flow
// graph in the Advanced branch: the mockup is a document-flow layout, not a node graph. Selection,
// create (+arc/+sub-arc/+chapter/+scene) and edit/archive (the drawer) are all preserved; the toolbar
// + drawer + tray still wrap it in PlanHubPanel. Windowing rides underneath unchanged (usePlanWindows).
import { useTranslation } from 'react-i18next';

import type { ArcPagination, LaneArc } from '../types';
import { FlowLane } from './FlowLane';

export interface LaneFlowViewProps {
  laneTree: LaneArc[];
  arcPagination: Record<string, ArcPagination>;
  selectedId: string | null;
  activeChapterId: string | null;
  onSelect: (id: string) => void;
  onToggleArc: (arcId: string) => void;
  onToggleChapter: (chapterNodeId: string) => void;
  onLoadMoreArc: (arcId: string) => void;
  onAddChapter: ((arcId: string) => void) | null;
  onAddScene: ((chapterNodeId: string, bookChapterId: string) => void) | null;
  onAddSubArc: ((parentArcId: string) => void) | null;
  addingChild: boolean;
  childError: string | null;
  /** PH15 find — cards whose title matches the toolbar query are RINGED (never filtered). undefined ⇒
   *  no active query. */
  matchedIds?: Set<string>;
  /** "Fit" — bumped to reset any lanes the writer has horizontally resized back to their default
   *  width (the flow view has no zoom to fit; resetting the lane widths is the honest equivalent). */
  fitSignal?: number;
}

const DOTTED: React.CSSProperties = {
  backgroundImage: 'radial-gradient(circle at 1px 1px, hsl(var(--border)/0.5) 1px, transparent 0)',
  backgroundSize: '22px 22px',
};

export function LaneFlowView({
  laneTree, arcPagination, selectedId, activeChapterId, onSelect, onToggleArc, onToggleChapter,
  onLoadMoreArc, onAddChapter, onAddScene, onAddSubArc, addingChild, childError, matchedIds, fitSignal,
}: LaneFlowViewProps) {
  const { t } = useTranslation('studio');

  return (
    <div data-testid="plan-hub-flow" className="flex h-full min-h-0 flex-col">
      {childError && (
        <div
          data-testid="flow-child-error"
          className="border-b border-destructive/40 bg-destructive/10 px-3 py-1 text-xs text-destructive"
        >
          {childError}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto p-4" style={DOTTED}>
        {laneTree.length === 0 ? (
          <p data-testid="flow-empty" className="p-6 text-center text-xs text-muted-foreground">
            {t('planHub.flow.empty', 'No storylines yet — add an arc from the toolbar to begin.')}
          </p>
        ) : (
          // Keyed on fitSignal so "Fit" remounts the lanes, discarding any user CSS-resize widths.
          <div key={fitSignal ?? 0}>
            {laneTree.map((arc) => (
              <FlowLane
                key={arc.id}
                arc={arc}
                arcPagination={arcPagination}
                selectedId={selectedId}
                activeChapterId={activeChapterId}
                matchedIds={matchedIds}
                onSelect={onSelect}
                onToggleArc={onToggleArc}
                onToggleChapter={onToggleChapter}
                onLoadMoreArc={onLoadMoreArc}
                onAddChapter={onAddChapter}
                onAddScene={onAddScene}
                onAddSubArc={onAddSubArc}
                addingChild={addingChild}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 24 Plan Hub v2 (H2.1) — the `plan-hub` dock panel: the whole package on the graph canvas.
// Renders the structure shell as depth-nested lanes + keyset-loaded chapter/scene windows +
// scene-link edges (React Flow, positions from the pure laneLayout — PH14). Logic lives in
// usePlanHub (the controller producing PlanHubView); this file only wires the controller to the
// canvas and self-registers/titles as a studio panel. Book-scoped (bookId from the studio host).
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { usePlanHub } from '@/features/plan-hub/hooks/usePlanHub';
import { PlanCanvas } from '@/features/plan-hub/components';

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

  return (
    <div data-testid="studio-plan-hub-panel" className="h-full w-full">
      <PlanCanvas
        layout={view.layout}
        edges={view.edges}
        overlay={view.overlay}
        conformance={view.conformance}
        unionState={view.unionState}
        selectedId={view.selectedId}
        onSelect={view.select}
        onToggleArc={view.toggleArc}
        onToggleChapter={view.toggleChapter}
      />
    </div>
  );
}

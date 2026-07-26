// Workflows dock panel (S-12 · G-WORKFLOWS) — the user's visible workflow recipes
// (System badged read-only, own editable): enable/disable (per-user) + delete (own).
// Reaches skills-parity for the workflow surface.
import type { IDockviewPanelProps } from 'dockview-react';
import { WorkflowsView } from '@/features/workflows/components/WorkflowsView';
import { useStudioPanel } from './useStudioPanel';
import { useStudioHost } from '../host/StudioHostProvider';

export function WorkflowsPanel(props: IDockviewPanelProps) {
  useStudioPanel('workflows', props.api);
  const { bookId } = useStudioHost();
  return (
    <div data-testid="studio-workflows-panel" className="h-full min-h-0 overflow-auto p-3">
      <WorkflowsView bookId={bookId} />
    </div>
  );
}

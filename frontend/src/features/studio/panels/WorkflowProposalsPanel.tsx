// Workflow-proposals inbox dock panel (S-12 · G-WORKFLOWS) — the pending workflow
// proposals an agent minted via registry_propose_workflow, reachable outside the chat
// that produced them. Approving here mints the workflow (closes the no-UI hole).
import type { IDockviewPanelProps } from 'dockview-react';
import { WorkflowProposalsView } from '@/features/workflows/components/WorkflowProposalsView';
import { useStudioPanel } from './useStudioPanel';

export function WorkflowProposalsPanel(props: IDockviewPanelProps) {
  useStudioPanel('workflow-proposals', props.api);
  return (
    <div data-testid="studio-workflow-proposals-panel" className="h-full min-h-0 overflow-auto p-3">
      <WorkflowProposalsView />
    </div>
  );
}

// Proposals inbox dock panel (§13b · U2) — the agent's skill proposals, reachable
// outside the chat that produced them. Same ProposalsView mounts on the route too.
import type { IDockviewPanelProps } from 'dockview-react';
import { ProposalsView } from '@/features/extensions/components/ProposalsView';
import { useStudioPanel } from './useStudioPanel';

export function ProposalsPanel(props: IDockviewPanelProps) {
  useStudioPanel('proposals', props.api);
  return (
    <div data-testid="studio-proposals-panel" className="h-full min-h-0 overflow-auto p-3">
      <ProposalsView />
    </div>
  );
}

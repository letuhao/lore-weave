// 17_translation_enrichment_sharing_settings_docks.md — Lore enrichment dock, panel 2/6.
// The review workspace (list ⇄ detail) — the e2e target capability. Thin wrapper (DOCK-2):
// mounts its own EnrichmentProvider scoped to host.bookId and renders ProposalsPanel unmodified.
// No prop-threading gap here: ProposalsPanel's context reads (selectedProposalId, projectFilter)
// are only ever consumed by ProposalsPanel/ProposalList themselves, not shared cross-panel.
import type { IDockviewPanelProps } from 'dockview-react';
import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { ProposalsPanel } from '@/features/enrichment/components/ProposalsPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function EnrichmentProposalsPanel(props: IDockviewPanelProps) {
  useStudioPanel('enrichment-proposals', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-enrichment-proposals-panel" className="h-full min-h-0 overflow-auto p-6">
      <EnrichmentProvider bookId={host.bookId}>
        <ProposalsPanel />
      </EnrichmentProvider>
    </div>
  );
}

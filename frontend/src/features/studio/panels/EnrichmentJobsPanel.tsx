// 17_translation_enrichment_sharing_settings_docks.md — Lore enrichment dock, panel 5/6.
// Job list + status + resume for the cost-cap-paused enrichment jobs. Thin wrapper (DOCK-2):
// mounts its own EnrichmentProvider scoped to host.bookId and renders JobsPanel unmodified.
import type { IDockviewPanelProps } from 'dockview-react';
import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { JobsPanel } from '@/features/enrichment/components/JobsPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function EnrichmentJobsPanel(props: IDockviewPanelProps) {
  useStudioPanel('enrichment-jobs', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-enrichment-jobs-panel" className="h-full min-h-0 overflow-auto p-6">
      <EnrichmentProvider bookId={host.bookId}>
        <JobsPanel />
      </EnrichmentProvider>
    </div>
  );
}

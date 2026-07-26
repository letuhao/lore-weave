// 17_translation_enrichment_sharing_settings_docks.md — Lore enrichment dock, panel 4/6.
// The corpus side: license-tagged source material for retrieval/recook. Thin wrapper (DOCK-2):
// mounts its own EnrichmentProvider scoped to host.bookId and renders SourcesPanel unmodified.
import type { IDockviewPanelProps } from 'dockview-react';
import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { SourcesPanel } from '@/features/enrichment/components/SourcesPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function EnrichmentSourcesPanel(props: IDockviewPanelProps) {
  useStudioPanel('enrichment-sources', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-enrichment-sources-panel" className="h-full min-h-0 overflow-auto p-6">
      <EnrichmentProvider bookId={host.bookId}>
        <SourcesPanel />
      </EnrichmentProvider>
    </div>
  );
}

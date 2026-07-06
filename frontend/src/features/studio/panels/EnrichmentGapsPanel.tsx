// 17_translation_enrichment_sharing_settings_docks.md — Lore enrichment dock, panel 3/6.
// Detect under-described entities + auto-enrich. Thin wrapper (DOCK-2): mounts its own
// EnrichmentProvider scoped to host.bookId and renders GapsPanel unmodified — GapsPanel itself
// carries the D-ENRICH-GAPS-NO-EXTRACT-CTA fix (a real "Extract entities now" button opening
// the shared ExtractionWizard, instead of a dead-end message) as part of this same task.
import type { IDockviewPanelProps } from 'dockview-react';
import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { GapsPanel } from '@/features/enrichment/components/GapsPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function EnrichmentGapsPanel(props: IDockviewPanelProps) {
  useStudioPanel('enrichment-gaps', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-enrichment-gaps-panel" className="h-full min-h-0 overflow-auto p-6">
      <EnrichmentProvider bookId={host.bookId}>
        <GapsPanel />
      </EnrichmentProvider>
    </div>
  );
}

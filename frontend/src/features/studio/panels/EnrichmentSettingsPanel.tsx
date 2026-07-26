// 17_translation_enrichment_sharing_settings_docks.md — Lore enrichment dock, panel 6/6.
// The per-book de-bias PROFILE authoring panel (worldview/language/era/voice + per-kind
// dimension overrides + AI-suggest). Thin wrapper (DOCK-2): mounts its own EnrichmentProvider
// scoped to host.bookId and renders SettingsPanel unmodified.
import type { IDockviewPanelProps } from 'dockview-react';
import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { SettingsPanel } from '@/features/enrichment/components/SettingsPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function EnrichmentSettingsPanel(props: IDockviewPanelProps) {
  useStudioPanel('enrichment-settings', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-enrichment-settings-panel" className="h-full min-h-0 overflow-auto p-6">
      <EnrichmentProvider bookId={host.bookId}>
        <SettingsPanel />
      </EnrichmentProvider>
    </div>
  );
}

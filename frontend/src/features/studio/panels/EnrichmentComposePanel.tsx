// 17_translation_enrichment_sharing_settings_docks.md — Lore enrichment dock, panel 1/6.
// EnrichmentView.tsx's 6-way `activePanel` tab switch (DOCK-8 violation) becomes 6 sibling
// dock panels; this is the "Tạo / Create" capability. Thin wrapper (DOCK-2): mounts its OWN
// EnrichmentProvider instance scoped to host.bookId (the provider is already route-agnostic —
// it just takes bookId as a prop, see EnrichmentTab.tsx) and renders the EXISTING ComposePanel
// unmodified.
//
// Prop-threading note: ComposePanel's "Use Gaps" mode button called
// `useEnrichmentContext().setActivePanel('gaps')` — meaningful inside EnrichmentView's shared
// tab strip, a silent no-op once split into an independent panel with its OWN provider instance
// (no sibling panel reads this panel's `activePanel` state). ComposePanel now accepts an optional
// `onUseGaps` override for exactly this case; here it routes to the real sibling dock panel.
import type { IDockviewPanelProps } from 'dockview-react';
import { EnrichmentProvider } from '@/features/enrichment/context/EnrichmentContext';
import { ComposePanel } from '@/features/enrichment/components/compose/ComposePanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function EnrichmentComposePanel(props: IDockviewPanelProps) {
  useStudioPanel('enrichment-compose', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-enrichment-compose-panel" className="h-full min-h-0 overflow-auto p-6">
      <EnrichmentProvider bookId={host.bookId}>
        <ComposePanel onUseGaps={() => host.openPanel('enrichment-gaps')} />
      </EnrichmentProvider>
    </div>
  );
}

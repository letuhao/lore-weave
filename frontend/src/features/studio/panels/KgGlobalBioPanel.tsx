// 14_kg_panels.md Phase B — kg-bio: user-scoped (global bio is user-level, not book-scoped,
// per K1/K7-adjacent tenancy note in the spec). Thin wrapper (DOCK-2) around GlobalBioTab,
// which already owns its own data (useSummaries) and its own DOCK-9-compliant dialogs
// (FormDialog reset-confirm here, VersionsPanel's FormDialog/ConfirmDialog fixed in Phase A).
// No book/project scoping — mirrors KnowledgeHubPanel.tsx's simplicity.
import type { IDockviewPanelProps } from 'dockview-react';
import { GlobalBioTab } from '@/features/knowledge/components/GlobalBioTab';
import { useStudioPanel } from './useStudioPanel';

export function KgGlobalBioPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-bio', props.api, { mcpToolPrefixes: ['kg_'] });

  return (
    <div data-testid="studio-kg-bio-panel" className="h-full min-h-0 overflow-auto p-4">
      <GlobalBioTab />
    </div>
  );
}

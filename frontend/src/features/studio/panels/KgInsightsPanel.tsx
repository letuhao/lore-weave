// 14_kg_panels.md Phase B — Mining Insights (K7): stays global-only, user-scoped. MiningInsightsTab
// takes no scoping prop today and is used identically from both KnowledgePage and
// ProjectDetailShell (per K7), so this panel is a thin wrapper (DOCK-2) with no project/book
// resolution — same tenancy tier as Settings/Usage, not book-scoped.
import type { IDockviewPanelProps } from 'dockview-react';
import { MiningInsightsTab } from '@/features/knowledge/components/MiningInsightsTab';
import { useStudioPanel } from './useStudioPanel';

export function KgInsightsPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-insights', props.api, { mcpToolPrefixes: ['kg_'] });

  return (
    <div data-testid="studio-kg-insights-panel" className="h-full min-h-0 overflow-auto p-4">
      <MiningInsightsTab />
    </div>
  );
}

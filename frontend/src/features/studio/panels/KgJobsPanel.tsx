// 14_kg_panels.md Phase B — kg-jobs panel: cross-project extraction jobs monitor.
// User-scoped (same tenancy tier as usage/notifications/settings — K1/K7-adjacent):
// `ExtractionJobsTab` takes NO project/book scoping prop today (it queries
// `useExtractionJobs()` directly, which is already cross-project per-user), so this
// panel is a thin wrapper (DOCK-2) with zero params, mirroring `KnowledgeHubPanel.tsx`'s
// simplicity — no book/project scoping needed.
import type { IDockviewPanelProps } from 'dockview-react';
import { ExtractionJobsTab } from '@/features/knowledge/components/ExtractionJobsTab';
import { useStudioPanel } from './useStudioPanel';

export function KgJobsPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-jobs', props.api, { mcpToolPrefixes: ['kg_'] });

  return (
    <div data-testid="studio-kg-jobs-panel" className="h-full min-h-0 overflow-auto p-4">
      <ExtractionJobsTab />
    </div>
  );
}

// 14_kg_panels.md Phase B — kg-privacy: user-scoped (K1), same tenancy tier as
// Settings/Usage. PrivacyTab is a GDPR export/delete surface over the caller's own
// account (`/v1/knowledge/user-data`) with no book/project scoping — this panel is a
// thin wrapper (DOCK-2), no forks, no params needed. PrivacyTab already renders its
// confirm dialog via `FormDialog` from `@/components/shared` (DOCK-9-compliant per the
// "already compliant" list in 14_kg_panels.md's DOCK-9 finding), so no adoption work
// is needed here.
import type { IDockviewPanelProps } from 'dockview-react';
import { PrivacyTab } from '@/features/knowledge/components/PrivacyTab';
import { useStudioPanel } from './useStudioPanel';

export function KgPrivacyPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-privacy', props.api, { mcpToolPrefixes: ['kg_'] });

  return (
    <div data-testid="studio-kg-privacy-panel" className="h-full min-h-0 overflow-auto p-4">
      <PrivacyTab />
    </div>
  );
}

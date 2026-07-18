// S5 · Divergence (dị bản) — the MANAGE panel for a book's what-if derivative Works.
// The whole divergence subsystem (schema, wizard, promotion, grounding-layer view) was
// reachable ONLY from the legacy ChapterEditorPage; a Studio-only user could not LIST,
// create, switch to, or archive a dị bản, and there are zero divergence MCP tools. This
// surfaces the list that already exists (candidates[]) with switch/archive + the create
// wizard, reusing the composition leaves (DivergenceWizard, useDerivativeContext).
import type { IDockviewPanelProps } from 'dockview-react';

import { useAuth } from '@/auth';
import { DivergenceManagerView } from '@/features/composition/components/DivergenceManagerView';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function DivergencePanel(props: IDockviewPanelProps) {
  useStudioPanel('divergence', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  return (
    <div className="h-full min-h-0">
      <DivergenceManagerView bookId={host.bookId} token={accessToken} />
    </div>
  );
}

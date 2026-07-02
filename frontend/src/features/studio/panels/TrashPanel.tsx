// #11 W2 · Trash dock panel — THIN wrapper over TrashPage in embedded mode (drops the page-only
// "back to books" breadcrumb; restore/purge behaviour is identical to the page).
import type { IDockviewPanelProps } from 'dockview-react';
import { TrashPage } from '@/pages/TrashPage';
import { useStudioPanel } from './useStudioPanel';

export function TrashPanel(props: IDockviewPanelProps) {
  useStudioPanel('trash', props.api);
  return (
    <div data-testid="studio-trash-panel" className="h-full min-h-0 overflow-auto p-4">
      <TrashPage embedded />
    </div>
  );
}

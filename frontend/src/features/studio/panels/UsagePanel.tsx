// #11 W2 · Usage dock panel — a THIN wrapper over the existing UsagePage (reuse AS-IS, no fork:
// the page is fully self-contained — no route hooks — so the panel only adds dock chrome).
// Pairs with the status-bar cost meter (F2): meter = ambient number, this panel = the truth.
import type { IDockviewPanelProps } from 'dockview-react';
import { UsagePage } from '@/pages/UsagePage';
import { useStudioPanel } from './useStudioPanel';

export function UsagePanel(props: IDockviewPanelProps) {
  useStudioPanel('usage', props.api);
  return (
    <div data-testid="studio-usage-panel" className="h-full min-h-0 overflow-auto">
      <UsagePage />
    </div>
  );
}

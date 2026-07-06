// 15_wiki_panels.md B1 — the `wiki` dock panel: a thin view over the SAME WikiWorkspace used by
// the classic WikiTab page (DOCK-2 — no fork).
import type { IDockviewPanelProps } from 'dockview-react';
import { WikiWorkspace } from '@/features/wiki/components/WikiWorkspace';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function WikiPanel(props: IDockviewPanelProps) {
  useStudioPanel('wiki', props.api);
  const host = useStudioHost();

  return (
    <div data-testid="studio-wiki-panel" className="h-full min-h-0 overflow-auto p-3">
      <WikiWorkspace bookId={host.bookId} />
    </div>
  );
}

// 13_glossary_panels.md Phase B — the merge-candidate review dock panel: extracted from
// GlossaryPanel's temporary internal view-switch (DOCK-8 debt) into its own catalog entry, per
// the Phase B fanout table. Thin wrapper — all merge logic stays in MergeCandidatePanel /
// useMergeCandidates (untouched). "Back to list" now navigates to the sibling `glossary` panel
// via the host instead of local view state.
import type { IDockviewPanelProps } from 'dockview-react';
import { MergeCandidatePanel } from '@/features/glossary/components/MergeCandidatePanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function GlossaryMergeCandidatesPanel(props: IDockviewPanelProps) {
  useStudioPanel('glossary-merge-candidates', props.api, { mcpToolPrefixes: ['glossary_'] });
  const host = useStudioHost();

  return (
    <div data-testid="studio-glossary-merge-candidates-panel" className="h-full min-h-0 overflow-auto">
      <MergeCandidatePanel bookId={host.bookId} onClose={() => host.openPanel('glossary')} />
    </div>
  );
}

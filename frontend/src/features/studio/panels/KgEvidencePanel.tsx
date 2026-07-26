// 14_kg_panels.md Phase B — the `kg-evidence` dock panel: thin wrapper over `RawDrawersTab`
// (K4 "shared capability, optional scope"). RawDrawersTab already renders identically whether
// `scopedProjectId` is set (book-scoped — hides the per-tab project `<select>`) or not (global
// cross-project browse, dropdown shown). ONE catalog entry; the CALLER decides which mode by
// passing (or omitting) `params.scopedProjectId` (F1 deep-link params contract) — this panel
// does not resolve a book/project itself.
import type { IDockviewPanelProps } from 'dockview-react';
import { RawDrawersTab } from '@/features/knowledge/components/RawDrawersTab';
import { useStudioPanel } from './useStudioPanel';

export function KgEvidencePanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-evidence', props.api, { mcpToolPrefixes: ['kg_'] });

  const scopedProjectId = props.params?.scopedProjectId as string | undefined;

  return (
    <div data-testid="studio-kg-evidence-panel" className="h-full min-h-0 overflow-auto p-4">
      <RawDrawersTab scopedProjectId={scopedProjectId} />
    </div>
  );
}

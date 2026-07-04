// 14_kg_panels.md Phase B — `kg-timeline` dock panel: thin wrapper over `TimelineTab` (DOCK-2 —
// no fork). K4 "shared capability, optional scope" — TimelineTab already accepts an optional
// `scopedProjectId` prop and renders identically whether it's set (book-scoped, opened e.g. from
// `kg-overview` or the `knowledge` hub with a project selected) or absent (global cross-project
// browse). This panel does NOT resolve a book/project itself — the caller decides scope by
// passing (or omitting) `params.scopedProjectId` (F1, DOCK-7).
import type { IDockviewPanelProps } from 'dockview-react';
import { TimelineTab } from '@/features/knowledge/components/TimelineTab';
import { useStudioPanel } from './useStudioPanel';

interface KgTimelinePanelParams {
  scopedProjectId?: string;
}

export function KgTimelinePanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-timeline', props.api, { mcpToolPrefixes: ['kg_'] });

  const scopedProjectId = (props.params as KgTimelinePanelParams | undefined)
    ?.scopedProjectId;

  return (
    <div data-testid="studio-kg-timeline-panel" className="h-full min-h-0 overflow-auto p-4">
      <TimelineTab scopedProjectId={scopedProjectId} />
    </div>
  );
}

// 14_kg_panels.md Phase B — `kg-gap` panel: thin wrapper around GapReportTab (DOCK-2), the
// glossary-gap report. Book-scoped ONLY (no global browse-all mode, per the spec) — resolves
// the book's KG project via useBookKnowledgeProject (A1/K5) instead of a route param (DOCK-7).
// Reuses existing i18n keys (kgOntology.page.noProject* / knowledge.project.loading) rather than
// adding new studio.json entries — locale files are out of scope for this slice.
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { GapReportTab } from '@/features/knowledge/components/GapReportTab';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { KgNoProjectState } from '@/features/knowledge/components/shell/KgNoProjectState';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function KgGapReportPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-gap', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();
  const { projectId, isLoading } = useBookKnowledgeProject(host.bookId);

  if (isLoading) {
    return (
      <div className="space-y-3 p-4" data-testid="kg-gap-panel-loading">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="m-4">
        <KgNoProjectState bookId={host.bookId} testId="kg-gap-no-project" />
      </div>
    );
  }

  return (
    <div data-testid="studio-kg-gap-panel" className="h-full min-h-0 overflow-auto p-4">
      <GapReportTab scopedProjectId={projectId} />
    </div>
  );
}

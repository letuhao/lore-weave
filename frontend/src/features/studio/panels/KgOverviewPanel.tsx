// 14_kg_panels.md Phase B — `kg-overview` panel: book-scoped project summary + quick actions.
// Thin wrapper over OverviewSection (DOCK-2 — no fork). Resolves "the book's knowledge
// project" via useBookKnowledgeProject (A1/K5) instead of a route param (DOCK-7 — no
// useParams/useNavigate/react-router Link here). Explore-graph and the book/world backlinks all go
// through host.openPanel/the studio link resolver instead of navigate() (DOCK-7).
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { OverviewSection } from '@/features/knowledge/components/shell/OverviewSection';
import { KgNoProjectState } from '@/features/knowledge/components/shell/KgNoProjectState';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { useTriageQueue } from '@/features/knowledge/hooks/useTriageQueue';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { useStudioPanel } from './useStudioPanel';

export function KgOverviewPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-overview', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();
  const { project, projectId, isLoading } = useBookKnowledgeProject(host.bookId);
  // S-05 — surface a "N need triage →" nudge that deep-links INTO the kg-triage
  // panel (spec B.2). The count fetch lives here (studio-specific); OverviewSection
  // stays presentational, so the classic route (no onOpenTriage) shows no nudge.
  const { groups: triageGroups } = useTriageQueue(projectId);
  const triageCount = triageGroups.reduce((n, g) => n + g.count, 0);

  if (isLoading) {
    return (
      <div data-testid="kg-overview-loading" className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="m-4">
        <KgNoProjectState bookId={host.bookId} testId="kg-overview-no-project" />
      </div>
    );
  }

  return (
    <div data-testid="studio-kg-overview-panel" className="h-full min-h-0 overflow-auto p-4">
      <OverviewSection
        project={project}
        onExploreGraph={() =>
          host.openPanel('kg-entities', { params: { scopedProjectId: projectId } })
        }
        onOpenBook={(bookId) =>
          followStudioLink(`/books/${bookId}`, host, { bookId: host.bookId })
        }
        onOpenWorld={(worldId) =>
          followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId })
        }
        triageCount={triageCount}
        onOpenTriage={() => host.openPanel('kg-triage')}
      />
    </div>
  );
}

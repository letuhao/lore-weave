// 14_kg_panels.md Phase B — `kg-graph`: the project subgraph canvas as a dock panel
// (book-scoped, DOCK-2 thin wrapper around ProjectGraphView — forks nothing). Resolves
// "the book's knowledge project" via useBookKnowledgeProject (A1/K5) — host.bookId doubles
// as the `bookId` prop ProjectGraphView wants, since a project's book_id IS the linked book.
// Loading/no-project states mirror KnowledgeOntologyTab.tsx's existing
// `kg-ontology-no-project` pattern (same 'kgOntology' i18n keys, no new locale entries needed).
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { ProjectGraphView } from '@/features/knowledge/components/ProjectGraphView';
import { KgNoProjectState } from '@/features/knowledge/components/shell/KgNoProjectState';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function KgGraphPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-graph', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();
  const { projectId, isLoading } = useBookKnowledgeProject(host.bookId);

  if (isLoading) {
    return (
      <div className="space-y-3 p-4" data-testid="kg-graph-loading">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="p-4">
        <KgNoProjectState bookId={host.bookId} testId="kg-ontology-no-project" />
      </div>
    );
  }

  return (
    <div data-testid="studio-kg-graph-panel" className="h-full min-h-0 overflow-auto p-4">
      <ProjectGraphView projectId={projectId} bookId={host.bookId} />
    </div>
  );
}

// 14_kg_panels.md Phase B — `kg-overview` panel: book-scoped project summary + quick actions.
// Thin wrapper over OverviewSection (DOCK-2 — no fork). Resolves "the book's knowledge
// project" via useBookKnowledgeProject (A1/K5) instead of a route param (DOCK-7 — no
// useParams/useNavigate/react-router Link here). Explore-graph and the book/world backlinks all go
// through host.openPanel/the studio link resolver instead of navigate() (DOCK-7).
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { OverviewSection } from '@/features/knowledge/components/shell/OverviewSection';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { useStudioPanel } from './useStudioPanel';

export function KgOverviewPanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-overview', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();
  // kgOntology already carries the "no project linked" copy for this exact tenancy
  // shape (KnowledgeOntologyTab's `kg-ontology-no-project` empty state) — reused
  // verbatim rather than adding a duplicate studio.json key for the same message.
  const { t } = useTranslation('kgOntology');
  const { project, projectId, isLoading } = useBookKnowledgeProject(host.bookId);

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
      <div
        className="m-4 rounded-lg border p-8 text-center"
        data-testid="kg-overview-no-project"
      >
        <p className="text-sm font-medium">{t('page.noProject')}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t('page.noProjectHelp')}</p>
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
      />
    </div>
  );
}

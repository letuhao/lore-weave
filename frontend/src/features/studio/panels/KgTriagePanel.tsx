// S-05 Part B — the `kg-triage` dock panel: the KG extraction-triage queue,
// book-scoped (resolves the book's KG project via useBookKnowledgeProject, A1/K5,
// like the other project-scoped KG panels — DOCK-7, no route param). Thin wrapper
// over TriageQueue (DOCK-2, no fork). The backend (routers/public/triage.py) was
// complete but had ZERO FE callers; this is the surface that consumes it.
//
// Glossary hand-off (promote_to_glossary_kind / demote_to_attribute) returns a
// needs_glossary deep-link; we follow it via the studio link resolver
// (followStudioLink) into the glossary surface — same shape as KgProposalsPanel.
import type { IDockviewPanelProps } from 'dockview-react';
import { Skeleton } from '@/components/shared';
import { TriageQueue } from '@/features/knowledge/components/TriageQueue';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { KgNoProjectState } from '@/features/knowledge/components/shell/KgNoProjectState';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { useStudioPanel } from './useStudioPanel';

export function KgTriagePanel(props: IDockviewPanelProps) {
  useStudioPanel('kg-triage', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();
  const { projectId, isLoading } = useBookKnowledgeProject(host.bookId);

  if (isLoading) {
    return (
      <div className="space-y-3 p-4" data-testid="kg-triage-panel-loading">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!projectId) {
    return (
      <div className="m-4">
        <KgNoProjectState bookId={host.bookId} testId="kg-triage-no-project" />
      </div>
    );
  }

  const onGlossaryHandoff = (needs: { book_id?: string | null; kinds: string[] }) => {
    const targetBook = needs.book_id ?? host.bookId;
    if (!targetBook) return;
    followStudioLink(`/books/${targetBook}/glossary`, host, { bookId: targetBook });
  };

  return (
    <div data-testid="studio-kg-triage-panel" className="h-full min-h-0 overflow-auto p-4">
      <TriageQueue
        projectId={projectId}
        bookId={host.bookId}
        onGlossaryHandoff={onGlossaryHandoff}
      />
    </div>
  );
}

// 14_kg_panels.md A2/K3 — the `knowledge` dock panel: a LAUNCHER only (DOCK-8's explicit
// escape hatch), never the host of any capability's content. Reuses ProjectsBrowser AS-IS
// (DOCK-2 — the same browse/search/sort/filter/create/archive/delete surface ProjectsTab's
// classic route renders).
//
// D-KG-HUB-EXTERNAL-OPEN fix (2026-07-05): opening a project used to ALWAYS go through the
// generic studio link resolver (F3 `followStudioLink`), which has no book-aware mapping for
// `/knowledge/projects/:id/*` (deliberately — see studioLinks.ts's comment: an arbitrary
// project id could belong to a DIFFERENT book than this studio's, and the kg-* panels only
// know how to render "the CURRENT book's project" via useBookKnowledgeProject, not an
// arbitrary given id). That meant EVERY project open — including this book's own, now-linked
// project, after Phase B shipped all 13 kg-* panels — fell through to "unmapped path" and
// popped the classic route in a new tab, which read as "left the studio" even though the
// original tab was untouched. Fix: when the clicked project IS this studio's book's project,
// open the in-studio `kg-overview` panel directly (this panel already knows the book_id
// relationship, so it can make that call precisely — no change needed to the generic
// resolver's deliberately-conservative path mapping). A different book's project still opens
// externally (correct — this studio can't render another book's KG panels).
import type { IDockviewPanelProps } from 'dockview-react';
import { ProjectsBrowser } from '@/features/knowledge/components/ProjectsBrowser';
import type { Project } from '@/features/knowledge/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { useStudioPanel } from './useStudioPanel';

export function KnowledgeHubPanel(props: IDockviewPanelProps) {
  useStudioPanel('knowledge', props.api, { mcpToolPrefixes: ['kg_'] });
  const host = useStudioHost();

  const onOpen = (project: Project) => {
    if (project.book_id === host.bookId) {
      host.openPanel('kg-overview', { params: { scopedProjectId: project.project_id } });
      return;
    }
    followStudioLink(`/knowledge/projects/${project.project_id}/overview`, host, {
      bookId: host.bookId,
    });
  };

  return (
    <div data-testid="studio-knowledge-hub-panel" className="h-full min-h-0 overflow-auto p-4">
      {/* D-KG-HUB-BOOK-SCOPE: default to this book's projects (toggle-able back to
          all books) — opened FROM this book's studio, so the global cross-book list
          made the user scroll past every other book's project to find this one. */}
      <ProjectsBrowser onOpen={onOpen} scopedBookId={host.bookId} />
    </div>
  );
}

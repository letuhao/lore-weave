// 14_kg_panels.md A2/K3 — the `knowledge` dock panel: a LAUNCHER only (DOCK-8's explicit
// escape hatch), never the host of any capability's content. Reuses ProjectsBrowser AS-IS
// (DOCK-2 — the same browse/search/sort/filter/create/archive/delete surface ProjectsTab's
// classic route renders), with ONE difference: opening a project goes through the studio
// link resolver (F3 `followStudioLink`) instead of navigate() (DOCK-7). Today no Phase-B KG
// panel is registered yet, so every open falls through F3's "unmapped app path" branch and
// opens the classic `/knowledge/projects/:id/overview` route in a new tab — not a silent
// no-op, and it upgrades to an in-tab `openPanel` automatically once a Phase-B panel adds
// its own path→panel mapping to studioLinks.ts (no change needed here).
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
    followStudioLink(`/knowledge/projects/${project.project_id}/overview`, host, {
      bookId: host.bookId,
    });
  };

  return (
    <div data-testid="studio-knowledge-hub-panel" className="h-full min-h-0 overflow-auto p-4">
      <ProjectsBrowser onOpen={onOpen} />
    </div>
  );
}

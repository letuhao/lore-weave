import { useNavigate } from 'react-router-dom';
import type { Project } from '../types';
import { ProjectsBrowser } from './ProjectsBrowser';

// 14_kg_panels.md A2 — thin route wrapper over ProjectsBrowser (DOCK-2/DOCK-7 extraction);
// the studio `knowledge` dock panel (KnowledgeHubPanel) renders the SAME browser with a
// different `onOpen` (the studio link resolver instead of navigate()).
export function ProjectsTab() {
  const navigate = useNavigate();
  const onOpen = (p: Project) => navigate(`/knowledge/projects/${p.project_id}/overview`);
  return <ProjectsBrowser onOpen={onOpen} />;
}

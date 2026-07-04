import { useMemo } from 'react';
import { Navigate, useNavigate, useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  LayoutDashboard,
  Users,
  Clock,
  Database,
  Inbox,
  AlertTriangle,
  BarChart2,
  Network,
  Share2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useProjects } from '@/features/knowledge/hooks/useProjects';
import { EntitiesTab } from '@/features/knowledge/components/EntitiesTab';
import { TimelineTab } from '@/features/knowledge/components/TimelineTab';
import { RawDrawersTab } from '@/features/knowledge/components/RawDrawersTab';
import { MiningInsightsTab } from '@/features/knowledge/components/MiningInsightsTab';
import { GapReportTab } from '@/features/knowledge/components/GapReportTab';
import { ProposalsInboxTab } from '@/features/knowledge/components/ProposalsInboxTab';
import { OverviewSection } from '@/features/knowledge/components/shell/OverviewSection';
import { ProjectSchemaSection } from '@/features/knowledge/components/shell/ProjectSchemaSection';
import { ProjectGraphView } from '@/features/knowledge/components/ProjectGraphView';

// C6 (G6) — Project-detail SHELL. The IA backbone for the book-workspace
// restructure: `/knowledge/projects/:projectId/:section` is HOME for a
// single project. `projectId` comes from the ROUTE (not a select-box);
// the project-scoped sub-tabs are route-driven <Link>s, NOT a
// conditional-unmount ternary inside one render — switching section is a
// navigation, so each section renders fresh by route. Scoped sub-tabs
// (Entities / Timeline / Evidence) receive `scopedProjectId` and hide
// their own project dropdown.
//
// Scope: Overview is real (reuses the project state card + config).
// Entities / Timeline / Evidence render the existing tabs scoped.
// Insights renders the mining tab. Proposals (C11) / Gap (C10) are real.
// Graph (C19) renders the explorable project subgraph canvas.

const SECTIONS = [
  'overview',
  'entities',
  'timeline',
  'evidence',
  'proposals',
  'gap',
  'insights',
  'schema',
  'graph',
] as const;

type Section = (typeof SECTIONS)[number];

const SECTION_DEFS: { id: Section; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'overview', icon: LayoutDashboard },
  { id: 'entities', icon: Users },
  { id: 'timeline', icon: Clock },
  { id: 'evidence', icon: Database },
  { id: 'proposals', icon: Inbox },
  { id: 'gap', icon: AlertTriangle },
  { id: 'insights', icon: BarChart2 },
  { id: 'schema', icon: Share2 },
  { id: 'graph', icon: Network },
];

function isSection(value: string | undefined): value is Section {
  return !!value && (SECTIONS as readonly string[]).includes(value);
}

export function ProjectDetailShell() {
  const { t } = useTranslation('knowledge');
  const navigate = useNavigate();
  const { projectId, section } = useParams<{
    projectId: string;
    section: string;
  }>();

  // useProjects is the single source for the project list (Track 1 keeps
  // ≤100 projects on one page; the C7 browser will paginate). We resolve
  // the route's project from that cache rather than a new per-project
  // fetch — no new BE per the G6 plan.
  const { items, isLoading } = useProjects(false);
  const project = useMemo(
    () => items.find((p) => p.project_id === projectId) ?? null,
    [items, projectId],
  );

  // Bad/empty section ⇒ canonicalize to overview (keeps deep-links sane).
  if (projectId && !isSection(section)) {
    return (
      <Navigate to={`/knowledge/projects/${projectId}/overview`} replace />
    );
  }

  const activeSection = section as Section;

  const exploreGraph = () =>
    navigate(`/knowledge/projects/${projectId}/entities`);

  return (
    <div className="mx-auto max-w-[1000px] px-6 py-6" data-testid="project-detail-shell">
      <Link
        to="/knowledge/projects"
        className="mb-3 inline-flex items-center gap-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
        data-testid="shell-back-to-projects"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        {t('shell.backToProjects')}
      </Link>

      <h1 className="mb-1 font-serif text-xl font-semibold" data-testid="shell-project-name">
        {project ? project.name : isLoading ? t('shell.loading') : t('shell.notFound')}
      </h1>

      <nav
        className="mb-6 mt-4 flex flex-wrap gap-0 border-b"
        role="tablist"
        aria-label={t('shell.sections.label')}
      >
        {SECTION_DEFS.map((sd) => {
          const Icon = sd.icon;
          return (
            <Link
              key={sd.id}
              to={`/knowledge/projects/${projectId}/${sd.id}`}
              role="tab"
              aria-selected={activeSection === sd.id}
              data-testid={`shell-tab-${sd.id}`}
              className={cn(
                '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                activeSection === sd.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t(`shell.sections.${sd.id}`)}
            </Link>
          );
        })}
      </nav>

      {/* Route-driven section render — only the active section mounts; a
          section switch is a navigation, not an in-place ternary unmount. */}
      {activeSection === 'overview' && (
        <OverviewSection
          project={project}
          onExploreGraph={exploreGraph}
          onOpenBook={(bookId) => navigate(`/books/${bookId}`)}
          onOpenWorld={(worldId) => navigate(`/worlds/${worldId}`)}
        />
      )}
      {activeSection === 'entities' && projectId && (
        <EntitiesTab scopedProjectId={projectId} />
      )}
      {activeSection === 'timeline' && projectId && (
        <TimelineTab scopedProjectId={projectId} />
      )}
      {activeSection === 'evidence' && projectId && (
        <RawDrawersTab scopedProjectId={projectId} />
      )}
      {activeSection === 'insights' && <MiningInsightsTab />}
      {activeSection === 'proposals' && (
        <ProposalsInboxTab
          bookId={project?.book_id ?? null}
          onOpenRow={(row) => navigate(row.deepLinkUrl)}
        />
      )}
      {activeSection === 'gap' && projectId && (
        <GapReportTab scopedProjectId={projectId} />
      )}
      {activeSection === 'schema' && projectId && (
        <ProjectSchemaSection projectId={projectId} bookId={project?.book_id ?? null} />
      )}
      {activeSection === 'graph' && projectId && (
        <ProjectGraphView projectId={projectId} bookId={project?.book_id ?? null} />
      )}
    </div>
  );
}

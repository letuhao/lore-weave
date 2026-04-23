import { Navigate, useParams, Link } from 'react-router-dom';
import { FolderOpen, User, Lock, Briefcase, Users, Clock, Database } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { ProjectsTab } from '@/features/knowledge/components/ProjectsTab';
import { GlobalBioTab } from '@/features/knowledge/components/GlobalBioTab';
import { PrivacyTab } from '@/features/knowledge/components/PrivacyTab';
import { ExtractionJobsTab } from '@/features/knowledge/components/ExtractionJobsTab';
import { EntitiesTab } from '@/features/knowledge/components/EntitiesTab';
import { TimelineTab } from '@/features/knowledge/components/TimelineTab';
import { RawDrawersTab } from '@/features/knowledge/components/RawDrawersTab';
import {
  MobileKnowledgePage,
  MobilePrivacyShell,
} from '@/features/knowledge/components/MobileKnowledgePage';
import { useIsMobile } from '@/features/knowledge/hooks/useIsMobile';

type Tab = 'projects' | 'jobs' | 'global' | 'entities' | 'timeline' | 'raw' | 'privacy';

// All 7 tabs are live as of K19e Cycle γ-b.
// K19b.2 jobs · K19d β entities · K19e β timeline · K19e γ-b raw.

const TAB_DEFS: { id: Tab; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'projects', icon: FolderOpen },
  { id: 'jobs', icon: Briefcase },
  { id: 'global', icon: User },
  { id: 'entities', icon: Users },
  { id: 'timeline', icon: Clock },
  { id: 'raw', icon: Database },
  { id: 'privacy', icon: Lock },
];

export function KnowledgePage() {
  const { t } = useTranslation('knowledge');
  const { tab } = useParams<{ tab: string }>();
  const isMobile = useIsMobile();

  if (!tab || !TAB_DEFS.some((td) => td.id === tab)) {
    return <Navigate to="/knowledge/projects" replace />;
  }

  const activeTab = tab as Tab;

  // K19f.1 — at <768px we swap the 7-tab shell for a single-column
  // scroll of the three primary sections (Global / Projects / Jobs).
  // Privacy gets a dedicated mobile shell with a back link — fixed in
  // post-/review-impl M1 because falling through to the desktop render
  // on mobile+privacy left the 7-tab nav overflowing the viewport.
  if (isMobile) {
    if (activeTab === 'privacy') {
      return <MobilePrivacyShell />;
    }
    return <MobileKnowledgePage />;
  }

  return (
    <div className="mx-auto max-w-[1000px] px-6 py-6">
      <h1 className="mb-1 font-serif text-xl font-semibold">{t('page.title')}</h1>
      <p className="mb-5 text-[13px] text-muted-foreground">
        {t('page.subtitle')}
      </p>

      <nav className="mb-6 flex gap-0 border-b" role="tablist" aria-label={t('page.tabs.label')}>
        {TAB_DEFS.map((td) => {
          const Icon = td.icon;
          return (
            <Link
              key={td.id}
              to={`/knowledge/${td.id}`}
              role="tab"
              aria-selected={activeTab === td.id}
              className={cn(
                '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                activeTab === td.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t(`page.tabs.${td.id}`)}
            </Link>
          );
        })}
      </nav>

      {activeTab === 'projects' && <ProjectsTab />}
      {activeTab === 'jobs' && <ExtractionJobsTab />}
      {activeTab === 'global' && <GlobalBioTab />}
      {activeTab === 'entities' && <EntitiesTab />}
      {activeTab === 'timeline' && <TimelineTab />}
      {activeTab === 'raw' && <RawDrawersTab />}
      {activeTab === 'privacy' && <PrivacyTab />}
    </div>
  );
}

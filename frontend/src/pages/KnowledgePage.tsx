import { Navigate, useParams, Link } from 'react-router-dom';
import { FolderOpen, User, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { ProjectsTab } from '@/features/knowledge/components/ProjectsTab';
import { GlobalBioTab } from '@/features/knowledge/components/GlobalBioTab';
import { PrivacyTab } from '@/features/knowledge/components/PrivacyTab';

type Tab = 'projects' | 'global' | 'privacy';

const TAB_DEFS: { id: Tab; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'projects', icon: FolderOpen },
  { id: 'global', icon: User },
  { id: 'privacy', icon: Lock },
];

export function KnowledgePage() {
  const { t } = useTranslation('knowledge');
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !TAB_DEFS.some((td) => td.id === tab)) {
    return <Navigate to="/knowledge/projects" replace />;
  }

  const activeTab = tab as Tab;

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
      {activeTab === 'global' && <GlobalBioTab />}
      {activeTab === 'privacy' && <PrivacyTab />}
    </div>
  );
}

import { Navigate, useParams, Link } from 'react-router-dom';
import { FolderOpen, User, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ProjectsTab } from '@/features/knowledge/components/ProjectsTab';
import { GlobalBioTab } from '@/features/knowledge/components/GlobalBioTab';
import { PrivacyTab } from '@/features/knowledge/components/PrivacyTab';

type Tab = 'projects' | 'global' | 'privacy';

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'projects', label: 'Projects', icon: FolderOpen },
  { id: 'global', label: 'Global', icon: User },
  { id: 'privacy', label: 'Privacy', icon: Lock },
];

export function MemoryPage() {
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !TABS.some((t) => t.id === tab)) {
    return <Navigate to="/memory/projects" replace />;
  }

  const activeTab = tab as Tab;

  return (
    <div className="mx-auto max-w-[1000px] px-6 py-6">
      <h1 className="mb-1 font-serif text-xl font-semibold">Memory</h1>
      <p className="mb-5 text-[13px] text-muted-foreground">
        Projects, global bio, and privacy controls for what the AI remembers.
      </p>

      <nav className="mb-6 flex gap-0 border-b" role="tablist" aria-label="Memory tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Link
              key={t.id}
              to={`/memory/${t.id}`}
              role="tab"
              aria-selected={activeTab === t.id}
              className={cn(
                '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                activeTab === t.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
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

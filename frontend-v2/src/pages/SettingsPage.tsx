import { Navigate, useParams, Link } from 'react-router-dom';
import { User, Cpu, Languages, BookOpen, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AccountTab } from '@/features/settings/AccountTab';
import { ProvidersTab } from '@/features/settings/ProvidersTab';
import { TranslationTab } from '@/features/settings/TranslationTab';
import { ReadingTab } from '@/features/settings/ReadingTab';
import { LanguageTab } from '@/features/settings/LanguageTab';

type Tab = 'account' | 'providers' | 'translation' | 'reading' | 'language';

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'account', label: 'Account', icon: User },
  { id: 'providers', label: 'Model Providers', icon: Cpu },
  { id: 'translation', label: 'Translation', icon: Languages },
  { id: 'reading', label: 'Reading', icon: BookOpen },
  { id: 'language', label: 'Language', icon: Globe },
];

export function SettingsPage() {
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !TABS.some((t) => t.id === tab)) {
    return <Navigate to="/settings/account" replace />;
  }

  const activeTab = tab as Tab;

  return (
    <div className="mx-auto max-w-[800px] px-6 py-6">
      <h1 className="mb-5 font-serif text-xl font-semibold">Settings</h1>

      {/* Tab bar */}
      <nav className="mb-6 flex gap-0 border-b" role="tablist" aria-label="Settings tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Link
              key={t.id}
              to={`/settings/${t.id}`}
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

      {/* Tab content */}
      {activeTab === 'account' && <AccountTab />}
      {activeTab === 'providers' && <ProvidersTab />}
      {activeTab === 'translation' && <TranslationTab />}
      {activeTab === 'reading' && <ReadingTab />}
      {activeTab === 'language' && <LanguageTab />}
    </div>
  );
}

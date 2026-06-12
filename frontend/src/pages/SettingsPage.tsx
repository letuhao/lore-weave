import { Navigate, useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { User, Cpu, Languages, BookOpen, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AccountTab } from '@/features/settings/AccountTab';
import { ProvidersTab } from '@/features/settings/ProvidersTab';
import { TranslationTab } from '@/features/settings/TranslationTab';
import { ReadingTab } from '@/features/settings/ReadingTab';
import { LanguageTab } from '@/features/settings/LanguageTab';

type Tab = 'account' | 'providers' | 'translation' | 'reading' | 'language';

const TABS: { id: Tab; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'account', icon: User },
  { id: 'providers', icon: Cpu },
  { id: 'translation', icon: Languages },
  { id: 'reading', icon: BookOpen },
  { id: 'language', icon: Globe },
];

export function SettingsPage() {
  const { t } = useTranslation('settings');
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !TABS.some((tb) => tb.id === tab)) {
    return <Navigate to="/settings/account" replace />;
  }

  const activeTab = tab as Tab;

  return (
    <div className="mx-auto max-w-[800px] px-6 py-6">
      <h1 className="mb-5 font-serif text-xl font-semibold">{t('page.title')}</h1>

      {/* Tab bar */}
      <nav className="mb-6 flex gap-0 border-b" role="tablist" aria-label={t('page.tabs_aria')}>
        {TABS.map((tb) => {
          const Icon = tb.icon;
          return (
            <Link
              key={tb.id}
              to={`/settings/${tb.id}`}
              role="tab"
              aria-selected={activeTab === tb.id}
              className={cn(
                '-mb-px flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                activeTab === tb.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t(`page.tab.${tb.id}`)}
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

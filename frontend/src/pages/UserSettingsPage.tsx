import { Navigate, useParams, Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { AccountSection } from '@/components/settings/AccountSection';
import { ProvidersSection } from '@/components/settings/ProvidersSection';
import { TranslationSection } from '@/components/settings/TranslationSection';

type Tab = 'account' | 'providers' | 'translation';

const tabs: { id: Tab; label: string }[] = [
  { id: 'account', label: 'Account' },
  { id: 'providers', label: 'Model providers' },
  { id: 'translation', label: 'Translation' },
];

export function UserSettingsPage() {
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !tabs.some((t) => t.id === tab)) {
    return <Navigate to="/settings/account" replace />;
  }

  const activeTab = tab as Tab;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      {/* Tab bar */}
      <nav className="flex gap-1 border-b">
        {tabs.map((t) => (
          <Link
            key={t.id}
            to={`/settings/${t.id}`}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              activeTab === t.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      {/* Tab content */}
      <div>
        {activeTab === 'account' && <AccountSection />}
        {activeTab === 'providers' && <ProvidersSection />}
        {activeTab === 'translation' && <TranslationSection />}
      </div>
    </div>
  );
}

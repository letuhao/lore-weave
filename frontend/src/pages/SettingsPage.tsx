import { Navigate, useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { settingsTabsFor, SettingsTabContent, type SettingsTabId } from '@/features/settings/tabs';

export function SettingsPage() {
  const { t } = useTranslation('settings');
  const { tab } = useParams<{ tab: string }>();
  const { user } = useAuth();

  // Q-GATE lives in the shared registry: the public-MCP tab only appears when the platform
  // flag is on. When off, a deep link to /settings/mcp falls through to the redirect below.
  const tabs = settingsTabsFor(user?.public_mcp_enabled);

  if (!tab || !tabs.some((tb) => tb.id === tab)) {
    return <Navigate to="/settings/account" replace />;
  }

  const activeTab = tab as SettingsTabId;

  return (
    <div className="mx-auto max-w-[800px] px-6 py-6">
      <h1 className="mb-5 font-serif text-xl font-semibold">{t('page.title')}</h1>

      {/* Tab bar */}
      <nav className="mb-6 flex gap-0 border-b" role="tablist" aria-label={t('page.tabs_aria')}>
        {tabs.map((tb) => {
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
      <SettingsTabContent tab={activeTab} />
    </div>
  );
}

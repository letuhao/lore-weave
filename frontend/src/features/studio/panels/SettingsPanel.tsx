// #11 W2 · Settings dock panel — VS Code precedent: settings opens as a tab, not a route hop.
// Reuses the six settings tab components AS-IS; what differs from SettingsPage is ONLY tab
// state: route (`/settings/:tab`) becomes internal state seeded/updated by dock `params.tab`
// (the F1 deep-link seam — the palette or the link resolver can open straight to a tab).
// Keeps the Q-GATE: the public-MCP tab only exists when the platform flag is on.
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { User, Cpu, Languages, BookOpen, Globe, KeyRound } from 'lucide-react';
import type { IDockviewPanelProps } from 'dockview-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { AccountTab } from '@/features/settings/AccountTab';
import { ProvidersTab } from '@/features/settings/ProvidersTab';
import { TranslationTab } from '@/features/settings/TranslationTab';
import { ReadingTab } from '@/features/settings/ReadingTab';
import { LanguageTab } from '@/features/settings/LanguageTab';
import { McpAccessTab } from '@/features/settings/McpAccessTab';
import { useStudioPanel } from './useStudioPanel';

type Tab = 'account' | 'providers' | 'translation' | 'reading' | 'language' | 'mcp';

const BASE_TABS: { id: Tab; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'account', icon: User },
  { id: 'providers', icon: Cpu },
  { id: 'translation', icon: Languages },
  { id: 'reading', icon: BookOpen },
  { id: 'language', icon: Globe },
];

const isTab = (v: unknown): v is Tab =>
  typeof v === 'string' && ['account', 'providers', 'translation', 'reading', 'language', 'mcp'].includes(v);

export function SettingsPanel(props: IDockviewPanelProps) {
  useStudioPanel('settings', props.api);
  const { t } = useTranslation('settings');
  const { user } = useAuth();

  const tabs = user?.public_mcp_enabled
    ? [...BASE_TABS, { id: 'mcp' as Tab, icon: KeyRound }]
    : BASE_TABS;

  // dockview re-renders with new props.params on updateParameters — derive the deep-linked tab
  // at render time (no effect): a NEW params.tab value switches the tab; local clicks still win
  // until the next deep-link.
  const paramTab = isTab((props.params as { tab?: unknown } | undefined)?.tab)
    ? ((props.params as { tab: Tab }).tab)
    : null;
  const [tab, setTab] = useState<Tab>(paramTab ?? 'account');
  const lastParamTab = useRef(paramTab);
  if (paramTab !== lastParamTab.current) {
    lastParamTab.current = paramTab;
    if (paramTab && paramTab !== tab) setTab(paramTab);
  }

  // The Q-GATE can hide 'mcp' after a deep-link raced the user flag — fall back visibly.
  const activeTab = tabs.some((tb) => tb.id === tab) ? tab : 'account';

  return (
    <div data-testid="studio-settings-panel" className="flex h-full min-h-0 flex-col">
      <nav className="flex flex-shrink-0 gap-0 border-b px-3" role="tablist" aria-label={t('page.tabs_aria')}>
        {tabs.map((tb) => {
          const Icon = tb.icon;
          return (
            <button
              key={tb.id}
              type="button"
              role="tab"
              data-testid={`studio-settings-tab-${tb.id}`}
              aria-selected={activeTab === tb.id}
              onClick={() => setTab(tb.id)}
              className={cn(
                '-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-[12px] font-medium transition-colors',
                activeTab === tb.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t(`page.tab.${tb.id}`)}
            </button>
          );
        })}
      </nav>

      <div className="min-h-0 flex-1 overflow-auto px-4 py-4">
        {activeTab === 'account' && <AccountTab />}
        {activeTab === 'providers' && <ProvidersTab />}
        {activeTab === 'translation' && <TranslationTab />}
        {activeTab === 'reading' && <ReadingTab />}
        {activeTab === 'language' && <LanguageTab />}
        {activeTab === 'mcp' && <McpAccessTab />}
      </div>
    </div>
  );
}

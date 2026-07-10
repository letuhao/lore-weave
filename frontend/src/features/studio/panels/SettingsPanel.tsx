// #11 W2 · Settings dock panel — VS Code precedent: settings opens as a tab, not a route hop.
// Reuses the settings tab components AS-IS via the shared registry (`features/settings/tabs`);
// what differs from SettingsPage is ONLY tab state: route (`/settings/:tab`) becomes internal
// state seeded/updated by dock `params.tab` (the F1 deep-link seam — the palette or the link
// resolver can open straight to a tab). Keeps the Q-GATE: the public-MCP tab only exists when
// the platform flag is on.
//
// The tab list used to be duplicated here. It drifted: Chat & AI shipped to SettingsPage and
// was never added to this dock, so the Studio could not reach it at all. Both surfaces now
// derive from the one registry, and `settingsTabParity` proves they agree.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import {
  settingsTabsFor,
  isSettingsTab,
  SettingsTabContent,
  type SettingsTabId,
} from '@/features/settings/tabs';
import { useStudioPanel } from './useStudioPanel';

export function SettingsPanel(props: IDockviewPanelProps) {
  useStudioPanel('settings', props.api);
  const { t } = useTranslation('settings');
  const { user } = useAuth();

  const tabs = settingsTabsFor(user?.public_mcp_enabled);

  // Deep-linked tab (F1): seed from the addPanel params, then follow EVERY updateParameters via
  // the dockview event — it fires on each call, so a repeat deep-link to the SAME tab after the
  // user clicked elsewhere still lands (/review-impl MED — a render-derivation comparing values
  // would swallow it). Local clicks win between deep-links.
  const paramTab = isSettingsTab((props.params as { tab?: unknown } | undefined)?.tab)
    ? ((props.params as { tab: SettingsTabId }).tab)
    : null;
  const [tab, setTab] = useState<SettingsTabId>(paramTab ?? 'account');
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((p: Record<string, unknown> | undefined) => {
      const next = (p as { tab?: unknown } | undefined)?.tab;
      if (isSettingsTab(next)) setTab(next);
    });
    return () => d?.dispose?.();
  }, [props.api]);

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
        <SettingsTabContent tab={activeTab} />
      </div>
    </div>
  );
}

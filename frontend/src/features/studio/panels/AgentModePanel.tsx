// #20_agent_mode.md D1 — ONE Studio dock panel, 3 internal views (Runs list /
// New run / Mission control) exactly matching the mockup's nav-tabs. All 3
// views stay MOUNTED (CSS `hidden`, never a ternary unmount — this repo's FE
// rule) so switching tabs never resets in-flight New Run config or a
// selected-unit review in Mission control.
//
// hiddenFromPalette (catalog.ts): making this palette/agent-openable requires
// adding 'agent-mode' to chat-service's `ui_open_studio_panel` panel_id enum
// (services/**, out of scope for this session per the task's own
// "don't touch services/**" instruction) — panelCatalogContract.test.ts
// enforces palette-openable-set === that backend enum, so registering this as
// open here would either fail that test or require the out-of-scope backend
// edit. Tracked as a follow-up (see the session report); PlannerPanel links
// here in the meantime so the feature stays reachable without the palette.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { RunsListView } from './agentMode/RunsListView';
import { NewRunView } from './agentMode/NewRunView';
import { MissionControlView } from './agentMode/MissionControlView';

type AgentModeView = 'list' | 'new' | 'mission';

export function AgentModePanel(props: IDockviewPanelProps) {
  useStudioPanel('agent-mode', props.api);
  const { t } = useTranslation('composition');
  const host = useStudioHost();
  const [view, setView] = useState<AgentModeView>('list');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const openMission = (runId: string) => { setSelectedRunId(runId); setView('mission'); };

  const tabs: { id: AgentModeView; labelKey: string; label: string }[] = [
    { id: 'list', labelKey: 'authoringRun.navRuns', label: 'Runs' },
    { id: 'new', labelKey: 'authoringRun.navNewRun', label: 'New run' },
    { id: 'mission', labelKey: 'authoringRun.navMission', label: 'Mission control' },
  ];

  return (
    <div data-testid="studio-agent-mode-panel" className="flex h-full min-h-0 flex-col">
      <div className="flex gap-4 border-b px-3 pt-1.5" role="tablist" aria-label={t('authoringRun.navRuns', { defaultValue: 'Agent Mode' })}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={view === tab.id}
            data-testid={`agent-mode-tab-${tab.id}`}
            onClick={() => setView(tab.id)}
            className={`border-b-2 px-1 pb-2 text-xs font-semibold ${
              view === tab.id ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t(tab.labelKey, { defaultValue: tab.label })}
          </button>
        ))}
      </div>

      <div data-testid="agent-mode-view-list" className={`min-h-0 flex-1 overflow-auto ${view !== 'list' ? 'hidden' : ''}`}>
        <RunsListView bookId={host.bookId} onOpenRun={openMission} onNewRun={() => setView('new')} />
      </div>
      <div data-testid="agent-mode-view-new" className={`min-h-0 flex-1 overflow-auto ${view !== 'new' ? 'hidden' : ''}`}>
        <NewRunView bookId={host.bookId} onCreated={openMission} onCancel={() => setView('list')} />
      </div>
      <div data-testid="agent-mode-view-mission" className={`min-h-0 flex-1 overflow-auto ${view !== 'mission' ? 'hidden' : ''}`}>
        <MissionControlView bookId={host.bookId} runId={selectedRunId} onBack={() => setView('list')} />
      </div>
    </div>
  );
}

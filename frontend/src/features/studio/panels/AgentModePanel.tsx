// #20_agent_mode.md D1 — ONE Studio dock panel, 3 internal views (Runs list /
// New run / Mission control) exactly matching the mockup's nav-tabs. All 3
// views stay MOUNTED (CSS `hidden`, never a ternary unmount — this repo's FE
// rule) so switching tabs never resets in-flight New Run config or a
// selected-unit review in Mission control.
//
// Palette/agent-openable (catalog.ts has no hiddenFromPalette here): 'agent-mode'
// is registered in chat-service's `ui_open_studio_panel` panel_id enum +
// contracts/frontend-tools.contract.json (regenerated), so panelCatalogContract.test.ts's
// palette-openable-set === backend-enum check stays green (DOCK-6). Also still
// reachable via PlannerPanel's "Autonomous Agent Runs" link.
//
// D-AGENT-MODE-NOTIFY follow-up: also opened via a deep link with `{ runId }`
// params (the terminal-notification click path, studioLinks.ts AGENT_MODE_RUN_RE)
// — JobDetailPanel's params-retargeting pattern (props.params at mount +
// onDidParametersChange for an already-open singleton, DOCK-6).
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { RunsListView } from './agentMode/RunsListView';
import { NewRunView } from './agentMode/NewRunView';
import { MissionControlView } from './agentMode/MissionControlView';

type AgentModeView = 'list' | 'new' | 'mission';

interface AgentModeParams { runId?: unknown }

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function AgentModePanel(props: IDockviewPanelProps) {
  useStudioPanel('agent-mode', props.api);
  const { t } = useTranslation('composition');
  const host = useStudioHost();
  const initialRunId = str((props.params as AgentModeParams | undefined)?.runId);
  const [view, setView] = useState<AgentModeView>(initialRunId ? 'mission' : 'list');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialRunId);

  const openMission = (runId: string) => { setSelectedRunId(runId); setView('mission'); };

  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const runId = str((next as AgentModeParams | undefined)?.runId);
      if (runId) openMission(runId);
    });
    return () => d?.dispose?.();
  }, [props.api]);

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

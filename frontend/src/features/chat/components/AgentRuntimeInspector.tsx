import { useTranslation } from 'react-i18next';
import type { AgentSurfaceState } from '../types';

interface AgentRuntimeInspectorProps {
  state: AgentSurfaceState;
  expanded: boolean;
  onToggle: () => void;
  isStreaming: boolean;
}

const PHASE_LABELS: Record<AgentSurfaceState['phase'], string> = {
  Idle: 'Idle',
  Curated: 'Curated',
  SkillInjected: 'Skills',
  Discovering: 'Discovering…',
  Activated: 'Activated',
  ToolRunning: 'Running tool',
};

export function AgentRuntimeInspector({
  state,
  expanded,
  onToggle,
  isStreaming,
}: AgentRuntimeInspectorProps) {
  const { t } = useTranslation('chat');
  const phaseLabel = PHASE_LABELS[state.phase] ?? state.phase;
  const pulse = isStreaming && (state.phase === 'Discovering' || state.phase === 'ToolRunning');

  return (
    <div className="border-b border-border bg-muted/10 px-3 py-1.5" data-testid="agent-runtime-inspector">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 text-left"
      >
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            pulse ? 'animate-pulse bg-amber-500' : state.phase === 'Idle' ? 'bg-muted-foreground/40' : 'bg-emerald-500'
          }`}
        />
        <span className="text-xs font-medium text-foreground">
          {t('inspector.title', { defaultValue: 'Agent runtime' })}
        </span>
        <span className="text-xs text-muted-foreground" data-testid="agent-inspector-phase">
          {phaseLabel}
        </span>
        {state.running_tool && (
          <span className="truncate text-xs text-muted-foreground">· {state.running_tool}</span>
        )}
        <span className="ml-auto text-[10px] text-muted-foreground">{expanded ? '▾' : '▸'}</span>
      </button>
      {expanded && (
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] text-muted-foreground sm:grid-cols-3">
          <div>
            <dt>{t('inspector.pinned', { defaultValue: 'Pinned tools' })}</dt>
            <dd className="font-medium text-foreground">{state.pinned_count}</dd>
          </div>
          <div>
            <dt>{t('inspector.hot', { defaultValue: 'Hot seed' })}</dt>
            <dd className="font-medium text-foreground">{state.hot_seed_count}</dd>
          </div>
          <div>
            <dt>{t('inspector.activated', { defaultValue: 'Activated' })}</dt>
            <dd className="font-medium text-foreground">{state.activated_count}</dd>
          </div>
          {state.injected_skills.length > 0 && (
            <div className="col-span-2 sm:col-span-3">
              <dt>{t('inspector.skills', { defaultValue: 'Skills' })}</dt>
              <dd className="font-medium text-foreground">{state.injected_skills.join(', ')}</dd>
            </div>
          )}
          {state.last_find_tools_query && (
            <div className="col-span-2 sm:col-span-3">
              <dt>{t('inspector.last_search', { defaultValue: 'Last find_tools' })}</dt>
              <dd className="truncate font-medium text-foreground">{state.last_find_tools_query}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}

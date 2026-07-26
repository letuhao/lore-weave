import { useTranslation } from 'react-i18next';
import type { AgentSurfaceState, AgentSurfacePhase } from '../types';

interface AgentRuntimeInspectorProps {
  state: AgentSurfaceState;
  expanded: boolean;
  onToggle: () => void;
  isStreaming: boolean;
  /** W6: this turn's phase transitions (useAgentSurface accumulates them). */
  trail?: AgentSurfacePhase[];
}

// phase → i18n key suffix (inspector.phase.*).
const PHASE_KEYS: Record<AgentSurfaceState['phase'], string> = {
  Idle: 'idle',
  Curated: 'curated',
  SkillInjected: 'skills',
  Discovering: 'discovering',
  Activated: 'activated',
  ToolRunning: 'tool_running',
};

export function AgentRuntimeInspector({
  state,
  expanded,
  onToggle,
  isStreaming,
  trail,
}: AgentRuntimeInspectorProps) {
  const { t } = useTranslation('chat');
  const phaseLabel = (phase: AgentSurfaceState['phase']) =>
    PHASE_KEYS[phase] ? t(`inspector.phase.${PHASE_KEYS[phase]}`) : phase;
  const pulse = isStreaming && (state.phase === 'Discovering' || state.phase === 'ToolRunning');
  const adv = state.advertised;

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
          {t('inspector.title')}
        </span>
        <span className="text-xs text-muted-foreground" data-testid="agent-inspector-phase">
          {phaseLabel(state.phase)}
        </span>
        {state.running_tool && (
          <span className="truncate text-xs text-muted-foreground">· {state.running_tool}</span>
        )}
        <span className="ml-auto text-[10px] text-muted-foreground">{expanded ? '▾' : '▸'}</span>
      </button>
      {expanded && (
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] text-muted-foreground sm:grid-cols-3">
          <div>
            <dt>{t('inspector.pinned')}</dt>
            <dd className="font-medium text-foreground">{state.pinned_count}</dd>
          </div>
          <div>
            <dt>{t('inspector.hot')}</dt>
            <dd className="font-medium text-foreground">{state.hot_seed_count}</dd>
          </div>
          <div>
            <dt>{t('inspector.activated')}</dt>
            <dd className="font-medium text-foreground">{state.activated_count}</dd>
          </div>
          {adv && (
            <div className="col-span-2 sm:col-span-3" data-testid="agent-inspector-advertised">
              <dt>{t('inspector.advertised')}</dt>
              <dd className="font-medium text-foreground">
                {t('inspector.advertised_sizes', {
                  core: adv.core.length,
                  frontend: adv.frontend.length,
                  activated: adv.activated.length,
                })}
              </dd>
            </div>
          )}
          {trail && trail.length > 1 && (
            <div className="col-span-2 sm:col-span-3" data-testid="agent-inspector-trail">
              <dt>{t('inspector.trail')}</dt>
              <dd className="truncate font-medium text-foreground">
                {trail.map(phaseLabel).join(' → ')}
              </dd>
            </div>
          )}
          {state.injected_skills.length > 0 && (
            <div className="col-span-2 sm:col-span-3">
              <dt>{t('inspector.skills')}</dt>
              <dd className="font-medium text-foreground">{state.injected_skills.join(', ')}</dd>
            </div>
          )}
          {state.last_find_tools_query && (
            <div className="col-span-2 sm:col-span-3">
              <dt>{t('inspector.last_search')}</dt>
              <dd className="truncate font-medium text-foreground">{state.last_find_tools_query}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}

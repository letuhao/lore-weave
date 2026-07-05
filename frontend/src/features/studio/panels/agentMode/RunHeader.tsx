// #20_agent_mode.md §3 (Run header). FSM-legal action buttons only (cross-
// checked against authoring_runs.py's real route wiring via fsm.ts), D11
// health chips + budget bar, D4a mid-run pause-policy toggle.
import { useTranslation } from 'react-i18next';
import type { AuthoringRun } from '@/features/composition/authoringRuns/types';
import {
  actionsForRunStatus, breakerSeverity, isBudgetDanger, isHeartbeatStale, type RunAction,
} from '@/features/composition/authoringRuns/fsm';
import { runStatusBadgeClass } from './statusBadge';

interface Props {
  run: AuthoringRun;
  busy: boolean;
  startDisabledReason: string | null;
  onAction: (action: RunAction) => void;
  onTogglePausePolicy: (next: boolean) => void;
  pausePolicyBusy: boolean;
}

const ACTION_LABEL_KEYS: Record<RunAction, string> = {
  gate: 'authoringRun.header.gate',
  start: 'authoringRun.header.start',
  pause: 'authoringRun.header.pause',
  resume: 'authoringRun.header.resume',
  close: 'authoringRun.header.close',
  'revert-all': 'authoringRun.header.revertAll',
};
const ACTION_LABEL_DEFAULTS: Record<RunAction, string> = {
  gate: 'Gate →', start: 'Start', pause: 'Pause', resume: 'Resume', close: 'Close', 'revert-all': 'Revert all',
};

function healthChipClass(sev: 'ok' | 'warn' | 'danger'): string {
  if (sev === 'danger') return 'border-destructive text-destructive';
  if (sev === 'warn') return 'border-warning text-warning';
  return 'border-border text-muted-foreground';
}

// Friendly copy for the known breaker_state.reason values (fsm.ts's breakerSeverity
// classifies the same set). Falls back to the raw reason string for anything not yet
// mapped here, so an unrecognized future reason still surfaces instead of vanishing.
const BREAKER_REASON_LABEL_KEYS: Record<string, string> = {
  pause_after_each_unit: 'authoringRun.header.breakerReason.pauseAfterEachUnit',
  budget: 'authoringRun.header.breakerReason.budget',
  critic_severe: 'authoringRun.header.breakerReason.criticSevere',
  unit_failed: 'authoringRun.header.breakerReason.unitFailed',
  driver_crashed: 'authoringRun.header.breakerReason.driverCrashed',
};
const BREAKER_REASON_LABEL_DEFAULTS: Record<string, string> = {
  pause_after_each_unit: 'paused for review (after each unit)',
  budget: 'budget exhausted',
  critic_severe: 'critic flagged a severe issue',
  unit_failed: 'a unit failed',
  driver_crashed: 'driver crashed',
};

export function RunHeader({ run, busy, startDisabledReason, onAction, onTogglePausePolicy, pausePolicyBusy }: Props) {
  const { t } = useTranslation('composition');
  const actions = actionsForRunStatus(run.status);
  const breaker = breakerSeverity(run.breaker_state);
  // D11: only meaningful for a 'running' run — see fsm.ts's documented placeholder threshold.
  const heartbeatStale = isHeartbeatStale(run.status, run.driver_heartbeat_at);
  const spent = Number.parseFloat(run.spent_usd) || 0;
  const budget = Number.parseFloat(run.budget_usd) || 0;
  const danger = isBudgetDanger(spent, budget);
  const ratio = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;

  return (
    <div className="mb-3 rounded-md border p-3" data-testid="agent-mode-run-header">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[11px] text-muted-foreground" title={run.run_id}>
          run {run.run_id.slice(0, 8)}… · book {run.book_id.slice(0, 8)}… · level {run.level}
        </span>
        <span
          data-testid="agent-mode-status-badge"
          className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${runStatusBadgeClass(run.status)}`}
        >
          {run.status.replace('_', ' ')}
        </span>

        <div className="ml-auto flex flex-wrap gap-1.5">
          {actions.length === 0 && (
            <span className="text-[11px] italic text-muted-foreground">
              {t('authoringRun.header.closedNote', { defaultValue: 'Run closed — terminal, no further actions.' })}
            </span>
          )}
          {actions.map((action) => {
            const disabled = busy || (action === 'start' && !!startDisabledReason);
            return (
              <button
                key={action}
                type="button"
                data-testid={`agent-mode-action-${action}`}
                disabled={disabled}
                title={action === 'start' ? startDisabledReason ?? undefined : undefined}
                onClick={() => onAction(action)}
                className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${
                  action === 'revert-all'
                    ? 'border-destructive bg-destructive/10 text-destructive hover:bg-destructive/20'
                    : 'border-primary bg-primary/10 text-primary hover:bg-primary/20'
                }`}
              >
                {t(ACTION_LABEL_KEYS[action], { defaultValue: ACTION_LABEL_DEFAULTS[action] })}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5" data-testid="agent-mode-health-row">
        <span className={`rounded border px-2 py-0.5 text-[10px] ${healthChipClass(breaker)}`} data-testid="agent-mode-breaker-chip">
          {t('authoringRun.header.breakerLabel', { defaultValue: 'breaker' })}:{' '}
          {(() => {
            const reason = run.breaker_state?.reason as string | undefined;
            if (!reason) return t('authoringRun.header.breakerHealthy', { defaultValue: 'healthy' });
            const key = BREAKER_REASON_LABEL_KEYS[reason];
            return key ? t(key, { defaultValue: BREAKER_REASON_LABEL_DEFAULTS[reason] }) : reason;
          })()}
        </span>
        <span
          className={`rounded border px-2 py-0.5 text-[10px] ${healthChipClass(heartbeatStale ? 'danger' : 'ok')}`}
          data-testid="agent-mode-heartbeat-chip"
        >
          {t('authoringRun.header.heartbeatLabel', { defaultValue: 'heartbeat' })}:{' '}
          {run.status !== 'running'
            ? t('authoringRun.header.heartbeatNA', { defaultValue: 'n/a' })
            : heartbeatStale
              ? t('authoringRun.header.heartbeatStale', { defaultValue: 'STALE — driver may have died' })
              : t('authoringRun.header.heartbeatFresh', { defaultValue: 'fresh' })}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground" data-testid="agent-mode-budget-row">
        <span>{t('authoringRun.header.budgetLabel', { defaultValue: 'Budget' })}</span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
          <div
            data-testid="agent-mode-budget-bar-fill"
            className={`h-full rounded-full ${danger ? 'bg-destructive' : 'bg-primary'}`}
            style={{ width: `${ratio}%` }}
          />
        </div>
        <span className={`font-mono ${danger ? 'font-semibold text-destructive' : ''}`}>
          ${run.spent_usd} / ${run.budget_usd}
          {danger ? ` — ${t('authoringRun.header.budgetDanger', { defaultValue: 'near limit' })}` : ''}
        </span>
      </div>

      {run.pause_after_each_unit !== undefined && (
        <label className="mt-2 flex items-center gap-2 text-[11px]">
          <input
            type="checkbox"
            data-testid="agent-mode-pause-policy-toggle"
            checked={!!run.pause_after_each_unit}
            disabled={pausePolicyBusy}
            onChange={(e) => onTogglePausePolicy(e.target.checked)}
          />
          {t('authoringRun.header.pausePolicyLabel', { defaultValue: 'Auto-pause after each unit' })}
        </label>
      )}

      {run.status === 'failed' && run.error_message && (
        <div data-testid="agent-mode-error-banner" className="mt-2 rounded-md border border-destructive bg-destructive/10 p-2 text-[11px]">
          <span className="font-mono">{t('authoringRun.header.errorPrefix', { defaultValue: 'error_message:' })} {run.error_message}</span>
        </div>
      )}
    </div>
  );
}

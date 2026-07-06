// #20_agent_mode.md §1 (Runs list view). Real table of runs for the current
// book, one-active-run-per-book block banner (client-precomputed, never
// relying on the create call's 409 alone), and an honest empty state.
import { useTranslation } from 'react-i18next';
import { useAuthoringRunsList } from '@/features/composition/authoringRuns/hooks';
import { ACTIVE_RUN_STATUSES } from '@/features/composition/authoringRuns/fsm';
import { runStatusBadgeClass } from './statusBadge';

interface Props {
  bookId: string;
  onOpenRun: (runId: string) => void;
  onNewRun: () => void;
}

export function RunsListView({ bookId, onOpenRun, onNewRun }: Props) {
  const { t } = useTranslation('composition');
  const { data, isLoading, isError } = useAuthoringRunsList(bookId);
  const items = data?.items ?? [];
  const activeRun = items.find((r) => ACTIVE_RUN_STATUSES.includes(r.status)) ?? null;

  return (
    <div className="p-3" data-testid="agent-mode-runs-list">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('authoringRun.list.title', { defaultValue: 'Runs for this book' })}
        </h2>
        <button
          type="button"
          data-testid="agent-mode-new-run-button"
          disabled={!!activeRun}
          title={activeRun ? t('authoringRun.list.blockedTooltip', { defaultValue: 'Pause or close the active run first.' }) : undefined}
          onClick={onNewRun}
          className="rounded-md border border-primary bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t('authoringRun.list.newRun', { defaultValue: '+ New run' })}
        </button>
      </div>

      {activeRun && (
        <div
          data-testid="agent-mode-blocked-banner"
          className="mb-3 rounded-md border border-destructive bg-destructive/10 p-2.5 text-[11.5px] leading-relaxed"
        >
          {t('authoringRun.list.blockedBanner', {
            status: activeRun.status,
            defaultValue:
              'A run is already {{status}} for this book — only one active run per book is allowed. Open it below, or pause/close it first.',
          })}
        </div>
      )}

      {isLoading && (
        <p className="text-xs text-muted-foreground">
          {t('authoringRun.list.loading', { defaultValue: 'Loading runs…' })}
        </p>
      )}
      {isError && (
        <p className="text-xs text-destructive">
          {t('authoringRun.list.error', { defaultValue: 'Could not load runs.' })}
        </p>
      )}
      {!isLoading && !isError && items.length === 0 && (
        <p data-testid="agent-mode-runs-empty" className="text-xs text-muted-foreground">
          {t('authoringRun.list.empty', { defaultValue: 'No autonomous authoring runs yet for this book.' })}
        </p>
      )}

      {items.length > 0 && (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <th className="px-2 py-1.5">{t('authoringRun.list.colRun', { defaultValue: 'Run' })}</th>
              <th className="px-2 py-1.5">{t('authoringRun.list.colScope', { defaultValue: 'Scope' })}</th>
              <th className="px-2 py-1.5">{t('authoringRun.list.colStatus', { defaultValue: 'Status' })}</th>
              <th className="px-2 py-1.5">{t('authoringRun.list.colSpent', { defaultValue: 'Spent' })}</th>
              <th className="px-2 py-1.5">{t('authoringRun.list.colCreated', { defaultValue: 'Created' })}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr
                key={r.run_id}
                data-testid="agent-mode-run-row"
                onClick={() => onOpenRun(r.run_id)}
                className="cursor-pointer border-b hover:bg-secondary"
              >
                <td className="px-2 py-1.5 font-mono text-[10.5px]">{r.run_id.slice(0, 8)}…</td>
                <td className="px-2 py-1.5">
                  {t('authoringRun.list.scopeCount', { count: r.scope.length, defaultValue: '{{count}} chapters' })}
                </td>
                <td className="px-2 py-1.5">
                  <span className={`rounded-full px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wide ${runStatusBadgeClass(r.status)}`}>
                    {r.status.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-2 py-1.5 font-mono">${r.spent_usd} / ${r.budget_usd}</td>
                <td className="px-2 py-1.5 font-mono text-[10.5px]">
                  {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

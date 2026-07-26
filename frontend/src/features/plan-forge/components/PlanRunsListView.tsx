// D-PLANFORGE-NO-RESUME follow-up (mirrors #20_agent_mode.md's RunsListView) — a real table of
// plan runs for the current book, so reopening the Planner panel doesn't look like the run was
// never made. Unlike authoring_run there is NO one-active-run-per-book constraint here (the
// backend happily holds several 'proposed' runs for one book — verified against the real dev DB),
// so there is no blocked-banner concept to mirror; this is a plain list + click-to-open.
import { useTranslation } from 'react-i18next';
import { usePlanRunsList } from '../hooks/usePlanRunsList';
import type { PlanRunStatus } from '../types';
import { useAuth } from '@/auth';

interface Props {
  bookId: string;
  onOpenRun: (runId: string) => void;
  onNewRun: () => void;
}

function statusBadgeClass(status: PlanRunStatus): string {
  switch (status) {
    case 'failed': return 'bg-destructive/10 text-destructive';
    case 'compiled': return 'bg-success/10 text-success';
    case 'validated': return 'bg-info/10 text-info';
    case 'pending': return 'bg-accent/10 text-accent-foreground';
    default: return 'bg-secondary text-muted-foreground';
  }
}

export function PlanRunsListView({ bookId, onOpenRun, onNewRun }: Props) {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const { items, loading, error, showArchived, setShowArchived, archive, restore } =
    usePlanRunsList(bookId, accessToken ?? null);

  return (
    <div className="p-3" data-testid="plan-runs-list">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('planner.list.title', { defaultValue: 'Runs for this book' })}
        </h2>
        <label className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground">
          <input
            type="checkbox" data-testid="plan-runs-show-archived"
            checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)}
          />
          {t('planner.list.showArchived', { defaultValue: 'Show archived' })}
        </label>
        <button
          type="button"
          data-testid="plan-new-run-button"
          onClick={onNewRun}
          className="rounded-md border border-primary bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/20"
        >
          {t('planner.list.newRun', { defaultValue: '+ New propose' })}
        </button>
      </div>

      {loading && (
        <p data-testid="plan-runs-loading" className="text-xs text-muted-foreground">
          {t('planner.list.loading', { defaultValue: 'Loading runs…' })}
        </p>
      )}
      {error && (
        <p data-testid="plan-runs-error" className="text-xs text-destructive">
          {t('planner.list.error', { defaultValue: 'Could not load runs.' })}
        </p>
      )}
      {!loading && !error && items.length === 0 && (
        <p data-testid="plan-runs-empty" className="text-xs text-muted-foreground">
          {t('planner.list.empty', { defaultValue: 'No plan runs yet for this book.' })}
        </p>
      )}

      {items.length > 0 && (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <th className="px-2 py-1.5">{t('planner.list.colRun', { defaultValue: 'Run' })}</th>
              <th className="px-2 py-1.5">{t('planner.list.colMode', { defaultValue: 'Mode' })}</th>
              <th className="px-2 py-1.5">{t('planner.list.colStatus', { defaultValue: 'Status' })}</th>
              <th className="px-2 py-1.5">{t('planner.list.colCreated', { defaultValue: 'Created' })}</th>
              <th className="px-2 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr
                key={r.id}
                data-testid="plan-run-row"
                onClick={() => onOpenRun(r.id)}
                className="cursor-pointer border-b hover:bg-secondary"
              >
                <td className="px-2 py-1.5 font-mono text-[10.5px]">{r.id.slice(0, 8)}…</td>
                <td className="px-2 py-1.5 uppercase">{r.mode}</td>
                <td className="px-2 py-1.5">
                  <span className={`rounded-full px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wide ${statusBadgeClass(r.status)}`}>
                    {r.status}
                  </span>
                </td>
                <td className="px-2 py-1.5 font-mono text-[10.5px]">
                  {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {/* BE-4 — archive/restore; stopPropagation so the row-click doesn't open the run. */}
                  {r.is_archived ? (
                    <button
                      type="button" data-testid={`plan-run-restore-${r.id.slice(0, 8)}`}
                      onClick={(e) => { e.stopPropagation(); void restore(r.id); }}
                      className="rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-secondary"
                    >{t('planner.list.restore', { defaultValue: 'Restore' })}</button>
                  ) : (
                    <button
                      type="button" data-testid={`plan-run-archive-${r.id.slice(0, 8)}`}
                      onClick={(e) => { e.stopPropagation(); void archive(r.id); }}
                      className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    >{t('planner.list.archive', { defaultValue: 'Archive' })}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import { RotateCw } from 'lucide-react';
import { Skeleton, StatusBadge } from '@/components/shared';
import { useEnrichmentJobs } from '../hooks/useEnrichmentJobs';
import { useEnrichmentContext } from '../context/EnrichmentContext';
import { tierOf } from '../types';

/** Job list + status + resume (the cost-cap-paused jobs the background worker
 *  re-drives). Polls while a job is active. */
const VARIANT: Record<string, 'running' | 'pending' | 'completed' | 'failed'> = {
  running: 'running',
  estimating: 'running',
  pending: 'pending',
  paused: 'pending',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'failed',
};

export function JobsPanel() {
  const { t } = useTranslation('enrichment');
  const { bookId } = useEnrichmentContext();
  const { items, isLoading, resume } = useEnrichmentJobs(bookId);

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
        {t('jobs.none')}
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-card/40 text-[11px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left font-medium">{t('jobs.col.technique')}</th>
            <th className="px-3 py-2 text-left font-medium">{t('jobs.col.status')}</th>
            <th className="px-3 py-2 text-left font-medium">{t('jobs.col.proposals')}</th>
            <th className="px-3 py-2 text-left font-medium">{t('jobs.col.cost')}</th>
            <th className="px-3 py-2 text-left font-medium">{t('jobs.col.created')}</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {items.map((j) => (
            <tr key={j.job_id} className="hover:bg-secondary/30">
              <td className="px-3 py-2 font-mono text-xs">
                {tierOf(j.technique)} · {j.technique}
              </td>
              <td className="px-3 py-2">
                <StatusBadge
                  variant={VARIANT[j.status] ?? 'pending'}
                  label={t(`jobs.status.${j.status}`, { defaultValue: j.status })}
                />
                {/* #4: a failed job carries WHY it failed (e.g. gate-locked) — surface it. */}
                {j.status === 'failed' && j.error_message && (
                  <p
                    className="mt-1 max-w-[16rem] text-[10px] text-destructive"
                    data-testid={`job-error-${j.job_id}`}
                    title={j.error_message}
                  >
                    {j.error_message}
                  </p>
                )}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{j.proposals_total}</td>
              {/* #5: spent vs cap — the cost-cap-pause is the panel's whole point. */}
              <td className="px-3 py-2 font-mono text-xs" data-testid={`job-cost-${j.job_id}`}>
                ${j.actual_cost.toFixed(4)}
                {j.max_spend != null && (
                  <span className="text-muted-foreground"> / ${j.max_spend.toFixed(2)}</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {new Date(j.created_at).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right">
                {j.status === 'paused' && (
                  <button
                    onClick={() => void resume(j)}
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    <RotateCw className="h-3 w-3" /> {t('jobs.resume')}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import { Loader2, Pause, Play, X, CheckCircle2, AlertTriangle } from 'lucide-react';
import type { ResearchJob } from '../../researchApi';

/** Render-only status card for a kind's batch-research job (D-BATCH-RESEARCH-JOB). All
 *  state + actions come from the parent (KindResearchPanel); this only renders. */
export function ResearchJobCard({
  job,
  onPause,
  onResume,
  onCancel,
}: {
  job: ResearchJob;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation('glossaryTiering');
  // Progress tracks PAID searches against the planned cap (items_total). items_processed
  // counts visits incl. free skips and can exceed the cap on a skip-heavy re-run, so it's
  // the wrong numerator; a complete job pins 100% even if skips left searches_run < cap.
  const pct =
    job.status === 'complete'
      ? 100
      : job.items_total > 0
        ? Math.min(100, Math.round((job.searches_run / job.items_total) * 100))
        : 0;

  const btn = 'rounded border px-2 py-1 text-xs font-medium hover:bg-secondary disabled:opacity-40';
  return (
    <div className="space-y-2 rounded-lg border bg-card p-3 text-sm" data-testid={`research-job-${job.status}`}>
      <div className="flex items-center gap-2">
        {job.status === 'running' && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        {job.status === 'complete' && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
        {job.status === 'failed' && <AlertTriangle className="h-4 w-4 text-destructive" />}
        <span className="font-semibold">{t(`research.status.${job.status}`)}</span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {t('research.est_cost', { cost: job.est_cost_usd })}
        </span>
      </div>

      {(job.status === 'pending' || job.status === 'running' || job.status === 'paused_user') && (
        <>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-xs text-muted-foreground">
            {t('research.progress', { done: job.searches_run, total: job.items_total })} ·{' '}
            {t('research.sources', { count: job.sources_attached })}
          </p>
        </>
      )}

      {job.status === 'complete' && (
        <p className="text-xs text-muted-foreground">
          {t('research.complete_summary', { sources: job.sources_attached, entities: job.searches_run })}
        </p>
      )}

      {job.status === 'failed' && job.error_message && (
        <p className="text-xs text-destructive">{t('research.failed_prefix')}: {job.error_message}</p>
      )}

      <div className="flex gap-2 pt-0.5">
        {job.status === 'running' && (
          <button type="button" onClick={onPause} className={btn} data-testid="research-pause">
            <Pause className="mr-1 inline h-3 w-3" />
            {t('research.action.pause')}
          </button>
        )}
        {job.status === 'paused_user' && (
          <button type="button" onClick={onResume} className={btn} data-testid="research-resume">
            <Play className="mr-1 inline h-3 w-3" />
            {t('research.action.resume')}
          </button>
        )}
        {job.status === 'failed' && (
          <button type="button" onClick={onResume} className={btn} data-testid="research-retry">
            <Play className="mr-1 inline h-3 w-3" />
            {t('research.action.retry')}
          </button>
        )}
        {(job.status === 'pending' || job.status === 'running' || job.status === 'paused_user' || job.status === 'failed') && (
          <button type="button" onClick={onCancel} className={`${btn} text-destructive`} data-testid="research-cancel">
            <X className="mr-1 inline h-3 w-3" />
            {t('research.action.cancel')}
          </button>
        )}
      </div>
    </div>
  );
}

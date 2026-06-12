import { useTranslation } from 'react-i18next';
import { Loader2, Pause, XCircle, AlertTriangle, Play } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WikiGenJobStatus } from '../types';

/**
 * wiki-llm M7b-2a — the LLM-generation job progress strip. Renders the current
 * job's status + progress; offers Resume on a budget-paused job and Cancel on a
 * pending|paused one (the BE rejects a running cancel with 409 — so the button is
 * hidden there). Hidden entirely when there's no job, or once a job has cleanly
 * completed (nothing actionable left).
 */
export function WikiGenJobBanner({
  job,
  onResume,
  onCancel,
  busy,
}: {
  job: WikiGenJobStatus | null;
  onResume: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation('wiki');
  // Nothing to show for "no job" or a clean completion (the article list already
  // refreshed). paused/failed/running/pending all carry actionable info.
  if (!job || job.status === 'complete' || job.status === 'cancelled') return null;

  const { status } = job;
  const total = job.items_total ?? job.entity_count;
  const done = job.items_processed;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const canCancel = status === 'pending' || status === 'paused';

  const tone =
    status === 'failed'
      ? 'border-destructive/40 bg-destructive/8'
      : status === 'paused'
        ? 'border-amber-400/40 bg-amber-400/8'
        : 'border-primary/30 bg-primary/8';

  return (
    <div
      className={cn('mb-3 flex items-center gap-3 rounded-lg border px-4 py-2.5', tone)}
      role="status"
      data-testid="wiki-gen-banner"
    >
      <span className="shrink-0">
        {status === 'running' && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        {status === 'pending' && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {status === 'paused' && <Pause className="h-4 w-4 text-amber-400" />}
        {status === 'failed' && <AlertTriangle className="h-4 w-4 text-destructive" />}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs font-medium">
          <span>{t(`gen.status.${status}`)}</span>
          {(status === 'running' || status === 'paused') && (
            <span className="text-muted-foreground" data-testid="wiki-gen-progress">
              {t('gen.progress', { done, total })}
            </span>
          )}
        </div>
        {(status === 'running' || status === 'paused') && (
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className={cn('h-full rounded-full', status === 'paused' ? 'bg-amber-400' : 'bg-primary')}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
        {status === 'failed' && job.error_message && (
          <p className="mt-0.5 truncate text-[11px] text-destructive">{job.error_message}</p>
        )}
        {status === 'paused' && job.error_message === 'budget' && (
          <p className="mt-0.5 text-[11px] text-muted-foreground">{t('gen.pausedBudget')}</p>
        )}
      </div>

      <div className="flex shrink-0 gap-1.5">
        {status === 'paused' && (
          <button
            type="button"
            onClick={onResume}
            disabled={busy}
            data-testid="wiki-gen-resume"
            className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-50"
          >
            <Play className="h-3 w-3" />
            {t('gen.resume')}
          </button>
        )}
        {canCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            data-testid="wiki-gen-cancel"
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium hover:bg-secondary disabled:opacity-50"
          >
            <XCircle className="h-3 w-3" />
            {t('gen.cancel')}
          </button>
        )}
      </div>
    </div>
  );
}

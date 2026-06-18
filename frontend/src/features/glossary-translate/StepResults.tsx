import { useTranslation } from 'react-i18next';
import { CheckCircle2, XCircle, AlertTriangle, BookOpen, RotateCcw } from 'lucide-react';
import type { GlossaryTranslateJobStatus, GlossaryTranslateCostEstimate } from './types';
import { cn } from '@/lib/utils';

interface StepResultsProps {
  jobStatus: GlossaryTranslateJobStatus;
  costEstimate: GlossaryTranslateCostEstimate | null;
  onClose: () => void;
  onViewGlossary: () => void;
  /** Re-seed the wizard to step 0 to run another translation without reopening. */
  onRestart: () => void;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt || !finishedAt) return '';
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  return `${mins}m ${remSecs}s`;
}

export function StepResults({ jobStatus, costEstimate, onClose, onViewGlossary, onRestart }: StepResultsProps) {
  const { t } = useTranslation('glossaryTranslate');

  const s = jobStatus;
  const duration = formatDuration(s.started_at, s.finished_at);
  const isFailed = s.status === 'failed';
  const isCancelled = s.status === 'cancelled';
  const hasErrors = s.status === 'completed_with_errors' || s.failed_entities > 0;

  const StatusIcon = isFailed ? XCircle : isCancelled ? AlertTriangle : CheckCircle2;
  const statusColor = isFailed ? 'text-destructive' : isCancelled ? 'text-amber-400' : 'text-green-500';
  const noEntities = s.total_entities === 0;
  const titleKey = isFailed
    ? 'results.titleFailed'
    : isCancelled
      ? 'results.titleCancelled'
      : noEntities
        ? 'results.titleNoEntities'
        : hasErrors
          ? 'results.titleWithErrors'
          : 'results.title';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <StatusIcon className={cn('h-5 w-5', statusColor)} />
        <div>
          <p className="text-sm font-semibold">{t(titleKey)}</p>
          {duration && (
            <p className="text-[10px] text-muted-foreground">
              {t('results.duration', { count: s.total_entities, duration })}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-bold">{s.attrs_translated}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.attrsTranslated')}</p>
        </div>
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-bold text-muted-foreground">{s.attrs_skipped}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.attrsSkipped')}</p>
        </div>
        <div className="rounded-lg border border-green-500/20 p-3 text-center">
          <p className="text-xl font-bold text-green-500">{s.completed_entities}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.entitiesDone')}</p>
        </div>
        <div
          className={cn(
            'rounded-lg border p-3 text-center',
            s.failed_entities > 0 && 'border-destructive/20',
          )}
        >
          <p
            className={cn(
              'text-xl font-bold',
              s.failed_entities > 0 ? 'text-destructive' : 'text-muted-foreground',
            )}
          >
            {s.failed_entities}
          </p>
          <p className="text-[9px] text-muted-foreground">{t('results.entitiesFailed')}</p>
        </div>
      </div>

      {s.failed_entities > 0 && (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
            <span className="text-xs font-medium text-destructive">
              {t('results.partialFailure', { count: s.failed_entities })}
            </span>
          </div>
          {s.error_message && (
            <p className="text-[10px] text-muted-foreground">{s.error_message}</p>
          )}
        </div>
      )}

      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium">{t('results.tokenUsage')}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {formatTokens(s.total_input_tokens)} in + {formatTokens(s.total_output_tokens)} out
            </p>
          </div>
          {costEstimate && (
            <p className="text-[10px] text-muted-foreground">
              {t('results.estimated', {
                tokens: formatTokens(costEstimate.estimated_total_tokens),
              })}
            </p>
          )}
        </div>
      </div>

      {noEntities ? (
        <p className="text-[10px] text-muted-foreground rounded-md border px-3 py-2">
          {t('results.noEntities')}
        </p>
      ) : (
        <p className="text-[10px] text-muted-foreground">{t('results.machineNote')}</p>
      )}

      <div className="flex items-center justify-between gap-2 pt-1">
        <button
          onClick={onRestart}
          className="inline-flex items-center gap-1.5 rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          {t('results.runAgain')}
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onClose}
            className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            {t('results.close')}
          </button>
          <button
            onClick={onViewGlossary}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <BookOpen className="h-3.5 w-3.5" />
            {t('results.viewGlossary')}
          </button>
        </div>
      </div>
    </div>
  );
}

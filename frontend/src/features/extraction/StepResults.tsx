import { useTranslation } from 'react-i18next';
import { CheckCircle2, XCircle, AlertTriangle, BookOpen } from 'lucide-react';
import type { ExtractionJobStatus, CostEstimate } from './types';
import { cn } from '@/lib/utils';

interface StepResultsProps {
  jobStatus: ExtractionJobStatus;
  costEstimate: CostEstimate | null;
  onClose: () => void;
  onViewGlossary: () => void;
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

export function StepResults({ jobStatus, costEstimate, onClose, onViewGlossary }: StepResultsProps) {
  const { t } = useTranslation('extraction');

  const s = jobStatus;
  const duration = formatDuration(s.started_at, s.finished_at);
  const total = s.entities_created + s.entities_updated + s.entities_skipped;
  const isFailed = s.status === 'failed';
  const isCancelled = s.status === 'cancelled';
  const hasErrors = s.status === 'completed_with_errors';

  const StatusIcon = isFailed ? XCircle : isCancelled ? AlertTriangle : CheckCircle2;
  const statusColor = isFailed ? 'text-destructive' : isCancelled ? 'text-amber-400' : 'text-green-500';
  const titleKey = isFailed ? 'results.titleFailed' : isCancelled ? 'results.titleCancelled' : hasErrors ? 'results.titleWithErrors' : 'results.title';

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <StatusIcon className={cn('h-5 w-5', statusColor)} />
        <div>
          <p className="text-sm font-semibold">{t(titleKey)}</p>
          {duration && (
            <p className="text-[10px] text-muted-foreground">
              {t('results.duration', { count: s.total_chapters, duration })}
            </p>
          )}
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-5 gap-2">
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-bold">{total}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.totalFound')}</p>
        </div>
        <div className="rounded-lg border border-green-500/20 p-3 text-center">
          <p className="text-xl font-bold text-green-500">{s.entities_created}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.newEntities')}</p>
        </div>
        <div className="rounded-lg border border-primary/20 p-3 text-center">
          <p className="text-xl font-bold text-primary">{s.entities_updated}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.updatedEntities')}</p>
        </div>
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-bold text-muted-foreground">{s.entities_skipped}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.skippedEntities')}</p>
        </div>
        <div className={cn('rounded-lg border p-3 text-center', s.failed_chapters > 0 && 'border-destructive/20')}>
          <p className={cn('text-xl font-bold', s.failed_chapters > 0 ? 'text-destructive' : 'text-muted-foreground')}>{s.failed_chapters}</p>
          <p className="text-[9px] text-muted-foreground">{t('results.failedChapters')}</p>
        </div>
      </div>

      {/* Failed chapters detail */}
      {s.failed_chapters > 0 && (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
            <span className="text-xs font-medium text-destructive">
              {t('results.failedChaptersList', { count: s.failed_chapters })}
            </span>
          </div>
          <div className="space-y-0.5">
            {s.chapters
              .filter((ch) => ch.status === 'failed')
              .map((ch) => (
                <div key={ch.chapter_id} className="text-[10px] text-muted-foreground flex items-center justify-between">
                  <span>{ch.chapter_id.slice(0, 8)}… — {ch.error_message || 'Unknown error'}</span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Token usage */}
      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium">{t('results.tokenUsage')}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {formatTokens(s.total_input_tokens)} in + {formatTokens(s.total_output_tokens)} out = {formatTokens(s.total_input_tokens + s.total_output_tokens)} total
            </p>
          </div>
          {costEstimate && (
            <p className="text-[10px] text-muted-foreground">
              {t('results.estimated', { tokens: formatTokens(costEstimate.estimated_total_tokens) })}
            </p>
          )}
        </div>
      </div>

      {/* Draft note */}
      {s.entities_created > 0 && (
        <p className="text-[10px] text-muted-foreground">{t('results.draftNote')}</p>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 pt-1">
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
  );
}

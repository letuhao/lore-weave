import { useState } from 'react';
import { Loader2, X, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { extractionApi } from './api';
import { useExtractionPolling } from './useExtractionPolling';
import type { ExtractionJobStatus } from './types';

interface StepProgressProps {
  jobId: string;
  onComplete: (finalStatus: ExtractionJobStatus) => void;
}

export function StepProgress({ jobId, onComplete }: StepProgressProps) {
  const { t } = useTranslation('extraction');
  const { accessToken } = useAuth();
  const { status, isTerminal } = useExtractionPolling(jobId, accessToken);
  const [cancelling, setCancelling] = useState(false);

  // Auto-advance to results when terminal
  if (isTerminal && status) {
    // Use a microtask to avoid setState during render
    queueMicrotask(() => onComplete(status));
  }

  const handleCancel = async () => {
    if (!accessToken || cancelling) return;
    if (!confirm(t('progress.cancelConfirm'))) return;
    setCancelling(true);
    try {
      await extractionApi.cancelJob(jobId, accessToken);
      toast.success('Cancellation requested');
    } catch (e) {
      toast.error((e as Error).message);
    }
    setCancelling(false);
  };

  if (!status) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const pct = status.total_chapters > 0
    ? Math.round((status.completed_chapters / status.total_chapters) * 100)
    : 0;
  const total = status.entities_created + status.entities_updated + status.entities_skipped;

  return (
    <div className="space-y-4">
      {/* Header with cancel */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center animate-pulse">
            <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
          </div>
          <div>
            <p className="text-sm font-medium">{t('progress.title')}</p>
            <p className="text-[10px] text-muted-foreground">
              {t('progress.processing', {
                current: status.completed_chapters + 1,
                total: status.total_chapters,
              })}
            </p>
          </div>
        </div>
        {!isTerminal && (
          <button
            onClick={() => void handleCancel()}
            disabled={cancelling}
            className="inline-flex items-center gap-1 rounded-md border border-destructive/50 px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
          >
            {cancelling ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
            {t('progress.cancel')}
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-muted-foreground">{t('progress.chapterProgress')}</span>
          <span className="font-mono text-primary">{pct}%</span>
        </div>
        <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
          <span>{t('progress.chaptersCount', { completed: status.completed_chapters, total: status.total_chapters })}</span>
          {status.failed_chapters > 0 && (
            <span className="text-destructive flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {status.failed_chapters} failed
            </span>
          )}
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-green-500">{total}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.entitiesFound')}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-primary">{status.entities_created}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.newCreated')}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-amber-400">{status.entities_updated}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.updated')}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-muted-foreground">{status.entities_skipped}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.skipped')}</p>
        </div>
      </div>

      {/* Chapter log */}
      <div>
        <h3 className="text-xs font-medium mb-1.5">{t('progress.activityLog')}</h3>
        <div className="max-h-[180px] overflow-y-auto rounded-md border bg-card/30 p-2 font-mono text-[10px] space-y-0.5">
          {status.chapters.map((ch) => (
            <div
              key={ch.chapter_id}
              className={
                ch.status === 'completed' ? 'text-green-500' :
                ch.status === 'failed' ? 'text-destructive' :
                ch.status === 'running' ? 'text-primary' :
                'text-muted-foreground'
              }
            >
              {ch.chapter_id.slice(0, 8)}… {ch.status}
              {ch.entities_found != null && ` — ${ch.entities_found} entities`}
              {ch.error_message && ` — ${ch.error_message}`}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

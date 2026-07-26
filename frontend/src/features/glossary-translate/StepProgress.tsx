import { useState, useEffect, useRef } from 'react';
import { Loader2, X, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryTranslateApi } from './api';
import { useGlossaryTranslatePolling } from './useGlossaryTranslatePolling';
import type { GlossaryTranslateJobStatus } from './types';

interface StepProgressProps {
  jobId: string;
  onComplete: (finalStatus: GlossaryTranslateJobStatus) => void;
}

export function StepProgress({ jobId, onComplete }: StepProgressProps) {
  const { t } = useTranslation('glossaryTranslate');
  const { accessToken } = useAuth();
  const { status, isTerminal, error } = useGlossaryTranslatePolling(jobId, accessToken);
  const [cancelling, setCancelling] = useState(false);
  const completedRef = useRef(false);

  useEffect(() => {
    if (isTerminal && status && !completedRef.current) {
      completedRef.current = true;
      onComplete(status);
    }
  }, [isTerminal, status, onComplete]);

  const handleCancel = async () => {
    if (!accessToken || cancelling) return;
    if (!confirm(t('progress.cancelConfirm'))) return;
    setCancelling(true);
    try {
      await glossaryTranslateApi.cancelJob(jobId, accessToken);
      toast.success(t('progress.cancelRequested'));
    } catch (e) {
      toast.error((e as Error).message);
    }
    setCancelling(false);
  };

  // S1: a failing first poll used to leave `status` null forever → infinite spinner with the
  // error invisible. Surface it (the hook keeps polling, so a transient error clears itself).
  if (!status && error) {
    return (
      <div role="alert" data-testid="glossary-translate-poll-error" className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-xs text-destructive">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        {t('progress.pollFailed')}
      </div>
    );
  }

  if (!status) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const pct =
    status.total_entities > 0
      ? Math.round((status.completed_entities / status.total_entities) * 100)
      : 0;
  const noEntities = status.total_entities === 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center animate-pulse">
            <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
          </div>
          <div>
            <p className="text-sm font-medium">{t('progress.title')}</p>
            <p className="text-[10px] text-muted-foreground">
              {noEntities
                ? t('progress.noEntities')
                : t('progress.processing', {
                    current: status.completed_entities + 1,
                    total: status.total_entities,
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

      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-muted-foreground">{t('progress.entityProgress')}</span>
          <span className="font-mono text-primary">{pct}%</span>
        </div>
        <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
          <span>
            {t('progress.entitiesCount', {
              completed: status.completed_entities,
              total: status.total_entities,
            })}
          </span>
          {status.failed_entities > 0 && (
            <span className="text-destructive flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {t('progress.failedCount', { count: status.failed_entities })}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-green-500">{status.attrs_translated}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.attrsTranslated')}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-muted-foreground">{status.attrs_skipped}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.attrsSkipped')}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p className="text-xl font-bold text-primary">{status.completed_entities}</p>
          <p className="text-[10px] text-muted-foreground">{t('progress.entitiesDone')}</p>
        </div>
        <div className="rounded-lg border bg-card/50 p-3 text-center">
          <p
            className={`text-xl font-bold ${status.failed_entities > 0 ? 'text-destructive' : 'text-muted-foreground'}`}
          >
            {status.failed_entities}
          </p>
          <p className="text-[10px] text-muted-foreground">{t('progress.entitiesFailed')}</p>
        </div>
      </div>

      {status.error_message && (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-[10px] text-destructive">
          {status.error_message}
        </div>
      )}
    </div>
  );
}

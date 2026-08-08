import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pause, Play, RotateCcw, X } from 'lucide-react';

import { useJobControl } from '../hooks/useJobControl';
import type { ControlCap, JobControlAction } from '../types';

interface Props {
  service: string;
  jobId: string;
  /** State-aware caps for THIS job in its current status (from the row / live event). */
  controlCaps: ControlCap[];
  /** Server-side retry admission result, when the producer knows retry is blocked. */
  retryBlockedReason?: string | null;
  /** Failed extraction jobs expose a checkpoint-backed resume action. */
  resumeFromCheckpoint?: boolean;
  /** Compact = icon-only buttons (mobile cards / dense rows). */
  compact?: boolean;
}

// Past-tense success message per action (avoids the "cancel"+"d"="canceld" trap).
const SUCCESS: Record<JobControlAction, [string, string]> = {
  cancel: ['controls.cancelled', 'Cancelled.'],
  pause: ['controls.paused', 'Paused.'],
  resume: ['controls.resumed', 'Resumed.'],
  retry: ['controls.retried', 'Re-submitted as a new job.'],
};

/** Generalized lifecycle controls (the cross-service analog of campaigns'
 *  MonitorControls): render cancel/pause/resume strictly from control_caps —
 *  never inferred from kind. A stale-state 409 or 502 surfaces as a toast and the
 *  list re-syncs (useJobControl invalidates ['jobs']). */
export function JobControls({ service, jobId, controlCaps, compact, retryBlockedReason: serverRetryBlockedReason, resumeFromCheckpoint = false }: Props) {
  const { t } = useTranslation('jobs');
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [retryBlockedReason, setRetryBlockedReason] = useState<string | null>(serverRetryBlockedReason ?? null);

  // A retry is a server-side admission operation (benchmark, budget and active-job
  // gates are checked again).  Keep the action disabled after a definitive 409 so a
  // user cannot hammer an operation the backend has already rejected.  The next SSE
  // event or list refresh remounts/updates the row and clears this local guard.
  const retryErrorMessage = (e: Error): string | null => {
    const body = (e as Error & { body?: { detail?: unknown } }).body;
    const detail = body?.detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { code?: unknown; error_code?: unknown; message?: unknown };
      const code = String(d.error_code ?? d.code ?? '');
      const message = typeof d.message === 'string' ? d.message : '';
      if (code === 'benchmark_missing') {
        return t('controls.retryBenchmarkMissing', {
          defaultValue: 'Retry is unavailable: the embedding model has no benchmark. Run the model benchmark, then re-check.',
        });
      }
      if (code === 'benchmark_failed') {
        return t('controls.retryBenchmarkFailed', {
          defaultValue: 'Retry is unavailable: the embedding model failed its last benchmark.',
        });
      }
      if (message) return message;
    }
    return e.message || null;
  };

  const retryBlockedLabel = (reason: string): string => {
    const code = reason.split(':', 1)[0].trim();
    if (code === 'benchmark_missing') return t('controls.retryBenchmarkMissing', { defaultValue: 'Retry is unavailable: the embedding model has no benchmark. Run the model benchmark, then re-check.' });
    if (code === 'benchmark_failed') return t('controls.retryBenchmarkFailed', { defaultValue: 'Retry is unavailable: the embedding model failed its last benchmark.' });
    return reason;
  };
  const onError = (e: Error, args: { action: JobControlAction }) => {
    const code = (e as { status?: number }).status;
    if (code === 409) {
      const reason = args.action === 'retry' ? retryErrorMessage(e) : null;
      if (args.action === 'retry') setRetryBlockedReason(reason);
      toast.error(reason ?? t('controls.stale', { defaultValue: 'Job state changed — refreshed.' }));
    } else {
      toast.error(
        t('controls.actionFailed', { defaultValue: 'Action failed: {{error}}', error: e.message }),
      );
    }
    if (args.action === 'cancel') setConfirmCancel(false);
  };
  const ctl = useJobControl({
    onSuccess: (_j, args) => {
      const [k, d] = SUCCESS[args.action];
      toast.success(t(k, { defaultValue: d }));
      if (args.action === 'cancel') setConfirmCancel(false);
    },
    onError,
  });

  const run = (action: JobControlAction) => ctl.mutate({ service, jobId, action });
  const has = (c: ControlCap) => controlCaps.includes(c);
  const btn =
    'inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-sm hover:bg-accent disabled:opacity-50';
  if (controlCaps.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {has('retry') && !retryBlockedReason && (
        <span className="flex items-center gap-2">
          <button
            className={btn}
            onClick={() => run('retry')}
            disabled={ctl.isPending || retryBlockedReason !== null}
            title={retryBlockedReason ?? undefined}
            aria-label={t('controls.retry', { defaultValue: 'Retry' })}
          >
            <RotateCcw className="h-4 w-4" />
            {!compact && t('controls.retry', { defaultValue: 'Retry' })}
          </button>

        </span>
      )}
      {retryBlockedReason && (
        <span className="max-w-[28rem] text-xs text-destructive" role="status">
          {retryBlockedLabel(retryBlockedReason)}
        </span>
      )}
      {has('pause') && (
        <button
          className={btn}
          onClick={() => run('pause')}
          disabled={ctl.isPending}
          aria-label={t('controls.pause', { defaultValue: 'Pause' })}
        >
          <Pause className="h-4 w-4" />
          {!compact && t('controls.pause', { defaultValue: 'Pause' })}
        </button>
      )}
      {has('resume') && (
        <button
          className={btn}
          onClick={() => run('resume')}
          disabled={ctl.isPending}
          aria-label={t(resumeFromCheckpoint ? 'controls.resumeFromCheckpoint' : 'controls.resume', { defaultValue: resumeFromCheckpoint ? 'Resume from checkpoint' : 'Resume' })}
        >
          <Play className="h-4 w-4" />
          {!compact && t(resumeFromCheckpoint ? 'controls.resumeFromCheckpoint' : 'controls.resume', { defaultValue: resumeFromCheckpoint ? 'Resume from checkpoint' : 'Resume' })}
        </button>
      )}
      {has('cancel') &&
        (confirmCancel ? (
          <span className="flex items-center gap-2 text-sm">
            {t('controls.cancelConfirm', { defaultValue: 'Cancel job?' })}
            <button
              className="rounded-lg bg-destructive px-2.5 py-1 text-sm text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
              onClick={() => run('cancel')}
              disabled={ctl.isPending}
            >
              {t('controls.cancelYes', { defaultValue: 'Yes' })}
            </button>
            <button className={btn} onClick={() => setConfirmCancel(false)}>
              {t('controls.cancelNo', { defaultValue: 'No' })}
            </button>
          </span>
        ) : (
          <button
            className={`${btn} border-destructive/40 text-destructive`}
            onClick={() => setConfirmCancel(true)}
            aria-label={t('controls.cancel', { defaultValue: 'Cancel' })}
          >
            <X className="h-4 w-4" />
            {!compact && t('controls.cancel', { defaultValue: 'Cancel' })}
          </button>
        ))}
    </div>
  );
}

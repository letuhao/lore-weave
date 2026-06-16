import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pause, Play, X } from 'lucide-react';

import { useJobControl } from '../hooks/useJobControl';
import type { ControlCap, JobControlAction } from '../types';

interface Props {
  service: string;
  jobId: string;
  /** State-aware caps for THIS job in its current status (from the row / live event). */
  controlCaps: ControlCap[];
  /** Compact = icon-only buttons (mobile cards / dense rows). */
  compact?: boolean;
}

// Past-tense success message per action (avoids the "cancel"+"d"="canceld" trap).
const SUCCESS: Record<JobControlAction, [string, string]> = {
  cancel: ['controls.cancelled', 'Cancelled.'],
  pause: ['controls.paused', 'Paused.'],
  resume: ['controls.resumed', 'Resumed.'],
};

/** Generalized lifecycle controls (the cross-service analog of campaigns'
 *  MonitorControls): render cancel/pause/resume strictly from control_caps —
 *  never inferred from kind. A stale-state 409 or 502 surfaces as a toast and the
 *  list re-syncs (useJobControl invalidates ['jobs']). */
export function JobControls({ service, jobId, controlCaps, compact }: Props) {
  const { t } = useTranslation('jobs');
  const [confirmCancel, setConfirmCancel] = useState(false);

  const onError = (e: Error, args: { action: JobControlAction }) => {
    const code = (e as { status?: number }).status;
    if (code === 409) {
      toast.error(t('controls.stale', { defaultValue: 'Job state changed — refreshed.' }));
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
          aria-label={t('controls.resume', { defaultValue: 'Resume' })}
        >
          <Play className="h-4 w-4" />
          {!compact && t('controls.resume', { defaultValue: 'Resume' })}
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

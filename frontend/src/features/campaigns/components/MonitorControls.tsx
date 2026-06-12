import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pause, Play, X } from 'lucide-react';
import { campaignErrorCode } from '../api';
import {
  usePauseCampaign, useResumeCampaign, useCancelCampaign, useUpdateBudget,
} from '../hooks/useCampaignMutations';
import type { CampaignStatus } from '../types';

const TERMINAL = ['completed', 'failed', 'cancelled'];

interface Props {
  campaignId: string;
  status: CampaignStatus;
  budgetUsd: string | null;
}

/** S6 (view + control wiring) — status-aware lifecycle controls + inline budget edit. */
export function MonitorControls({ campaignId: id, status, budgetUsd }: Props) {
  const { t } = useTranslation('campaigns');
  const [budget, setBudget] = useState(budgetUsd ?? '');
  const [confirmCancel, setConfirmCancel] = useState(false);

  const ok = (k: string, d: string) => () => toast.success(t(k, { defaultValue: d }));
  const fail = (e: Error) => toast.error(t('monitor.actionFailed', { defaultValue: 'Action failed: {{error}}', error: e.message }));

  const pause = usePauseCampaign({ onSuccess: ok('monitor.paused', 'Paused.'), onError: fail });
  const cancel = useCancelCampaign({ onSuccess: () => { ok('monitor.cancelled', 'Cancelled.')(); setConfirmCancel(false); }, onError: fail });
  const resume = useResumeCampaign({
    onSuccess: ok('monitor.resumed', 'Resumed.'),
    onError: (e) => campaignErrorCode(e) === 'CAMPAIGN_OVER_BUDGET'
      ? toast.error(t('monitor.overBudget', { defaultValue: 'Over budget — raise the cap before resuming.' }))
      : fail(e),
  });
  const saveBudget = useUpdateBudget({ onSuccess: ok('monitor.budgetSaved', 'Budget updated.'), onError: fail });

  const isTerminal = TERMINAL.includes(status);
  const btn = 'inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50';

  return (
    <div className="flex flex-wrap items-center gap-3">
      {status === 'running' && (
        <button className={btn} onClick={() => pause.mutate(id)} disabled={pause.isPending}>
          <Pause className="h-4 w-4" />{t('monitor.pause', { defaultValue: 'Pause' })}
        </button>
      )}
      {status === 'paused' && (
        <button className={btn} onClick={() => resume.mutate(id)} disabled={resume.isPending}>
          <Play className="h-4 w-4" />{t('monitor.resume', { defaultValue: 'Resume' })}
        </button>
      )}
      {!isTerminal && (
        confirmCancel ? (
          <span className="flex items-center gap-2 text-sm">
            {t('monitor.cancelConfirm', { defaultValue: 'Cancel campaign?' })}
            <button className="rounded-lg bg-destructive px-3 py-1.5 text-sm text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
              onClick={() => cancel.mutate(id)} disabled={cancel.isPending}>
              {t('monitor.cancelYes', { defaultValue: 'Yes' })}
            </button>
            <button className={btn} onClick={() => setConfirmCancel(false)}>
              {t('monitor.cancelNo', { defaultValue: 'No' })}
            </button>
          </span>
        ) : (
          <button className={`${btn} border-destructive/40 text-destructive`} onClick={() => setConfirmCancel(true)}>
            <X className="h-4 w-4" />{t('monitor.cancel', { defaultValue: 'Cancel' })}
          </button>
        )
      )}
      {!isTerminal && (
        <span className="ml-auto flex items-center gap-2">
          <input className="w-28 rounded-md border bg-input px-2 py-1 text-sm outline-none focus:border-ring"
            value={budget} onChange={(e) => setBudget(e.target.value)}
            placeholder={t('monitor.budgetPlaceholder', { defaultValue: 'budget $' })} />
          <button className={btn} disabled={saveBudget.isPending || !budget.trim()}
            onClick={() => saveBudget.mutate({ campaignId: id, budgetUsd: budget.trim() })}>
            {t('monitor.saveBudget', { defaultValue: 'Set budget' })}
          </button>
        </span>
      )}
    </div>
  );
}

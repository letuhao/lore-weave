import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { useCampaign } from '../hooks/useCampaignQueries';
import { useCancelCampaign } from '../hooks/useCampaignMutations';
import { StatusBadge } from './StatusBadge';

const TERMINAL = ['completed', 'failed', 'cancelled'];

/** /campaigns/:id (view): read-only summary + a single Cancel control (S5c).
 *  Pause/resume + the per-chapter projection + fidelity scores land in S6. */
export function CampaignDetail({ campaignId }: { campaignId: string }) {
  const { t } = useTranslation('campaigns');
  const { data: c, isLoading, error } = useCampaign(campaignId);
  const [confirming, setConfirming] = useState(false);

  const cancel = useCancelCampaign({
    onSuccess: () => { toast.success(t('detail.cancelled', { defaultValue: 'Campaign cancelled.' })); setConfirming(false); },
    onError: (e) => toast.error(t('detail.cancelFailed', { defaultValue: 'Cancel failed: {{error}}', error: e.message })),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('detail.loading', { defaultValue: 'Loading…' })}</p>;
  if (error || !c) return <p className="text-sm text-destructive">{t('detail.error', { defaultValue: 'Failed to load campaign.' })}</p>;

  const cancellable = !TERMINAL.includes(c.status);
  const row = (k: string, v: React.ReactNode) => (
    <div className="flex justify-between gap-4 border-t py-2 text-sm">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Link to="/campaigns" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />{t('detail.back', { defaultValue: 'All campaigns' })}
      </Link>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{c.name}</h1>
        <StatusBadge status={c.status} />
      </div>

      <div className="rounded-lg border px-4">
        {row(t('detail.chapters', { defaultValue: 'Chapters' }), c.total_chapters)}
        {row(t('detail.spent', { defaultValue: 'Spent' }),
          c.budget_usd
            ? `$${Number(c.spent_usd).toFixed(4)} / $${Number(c.budget_usd).toFixed(2)}`
            : `$${Number(c.spent_usd).toFixed(4)}`)}
        {row(t('detail.targetLanguage', { defaultValue: 'Target language' }), c.target_language ?? '—')}
        {c.error_message && row(t('detail.lastError', { defaultValue: 'Last error' }), <span className="text-destructive">{c.error_message}</span>)}
      </div>

      {cancellable && (
        confirming ? (
          <div className="flex items-center gap-2">
            <span className="text-sm">{t('detail.cancelConfirm', { defaultValue: 'Cancel this campaign?' })}</span>
            <button onClick={() => cancel.mutate(c.campaign_id)} disabled={cancel.isPending}
              className="rounded-lg bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-60">
              {t('detail.cancelYes', { defaultValue: 'Yes, cancel' })}
            </button>
            <button onClick={() => setConfirming(false)}
              className="rounded-lg border px-3 py-1.5 text-sm hover:bg-accent">
              {t('detail.cancelNo', { defaultValue: 'Keep running' })}
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirming(true)}
            className="self-start rounded-lg border border-destructive/40 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/5">
            {t('detail.cancel', { defaultValue: 'Cancel campaign' })}
          </button>
        )
      )}
    </div>
  );
}

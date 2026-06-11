import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { campaignErrorCode } from '../../api';
import { useEstimateCampaign, useLaunchCampaign } from '../../hooks/useCampaignMutations';
import type {
  CreateCampaignPayload,
  EstimateRequest,
  EstimateResponse,
} from '../../types';

interface Props {
  buildEstimateRequest: () => EstimateRequest;
  buildCreatePayload: () => CreateCampaignPayload;
  budgetUsd: string;
  setBudget: (v: string) => void;
  onLaunched: (campaignId: string) => void;
  // G1 — bubble the estimate band up so the wizard persists it on launch (report).
  onEstimated?: (low: string, high: string) => void;
}

/** Step 4 (view): budget cap + on-demand cost/time estimate + Launch (create→start). */
export function ReviewStep({ buildEstimateRequest, buildCreatePayload, budgetUsd, setBudget, onLaunched, onEstimated }: Props) {
  const { t } = useTranslation('campaigns');
  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);

  const est = useEstimateCampaign({
    onSuccess: (r) => { setEstimate(r); onEstimated?.(r.estimated_usd_low, r.estimated_usd_high); },
    onError: (e) => toast.error(t('review.estimateFailed', { defaultValue: 'Estimate failed: {{error}}', error: e.message })),
  });

  const launch = useLaunchCampaign({
    onSuccess: (c) => { toast.success(t('review.launched', { defaultValue: 'Campaign launched.' })); onLaunched(c.campaign_id); },
    onError: (e) => {
      const code = campaignErrorCode(e);
      if (code === 'CAMPAIGN_EMBEDDING_CONFLICT') {
        toast.error(t('review.embeddingConflict', { defaultValue: 'Embedding change needs confirmation — go back to Models and tick the confirm box (or pick an empty project).' }));
      } else if (code === 'CAMPAIGN_OVER_BUDGET') {
        toast.error(t('review.overBudget', { defaultValue: 'Budget is below the current spend — raise it.' }));
      } else {
        toast.error(t('review.launchFailed', { defaultValue: 'Launch failed: {{error}}', error: e.message }));
      }
    },
  });

  const money = (v: string) => `$${Number(v).toFixed(4)}`;
  // #5 polish — compact token count (31.0M / 3.2K / 0).
  const tok = (n: number) =>
    n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);
  const fieldCls = 'w-40 rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring';

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('review.budget', { defaultValue: 'Budget cap (USD, optional)' })}
        </span>
        <input className={fieldCls} value={budgetUsd}
          onChange={(e) => setBudget(e.target.value)}
          placeholder={t('review.budgetPlaceholder', { defaultValue: 'blank = uncapped' })} />
        <span className="text-[11px] text-muted-foreground">
          {t('review.budgetHint', { defaultValue: 'The campaign auto-pauses once summed spend reaches this.' })}
        </span>
      </label>

      <button type="button"
        onClick={() => est.mutate(buildEstimateRequest())}
        disabled={est.isPending}
        className="self-start rounded-lg border border-primary/40 bg-primary/5 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/10 disabled:opacity-60">
        {est.isPending
          ? t('review.estimating', { defaultValue: 'Estimating…' })
          : t('review.estimate', { defaultValue: 'Estimate cost & time' })}
      </button>

      {estimate && (
        <div className="flex flex-col gap-2 rounded-lg border p-4">
          <div className="flex flex-wrap gap-6 text-sm">
            <span><strong>{t('review.cost', { defaultValue: 'Cost' })}:</strong> {money(estimate.estimated_usd_low)}–{money(estimate.estimated_usd_high)}</span>
            <span><strong>{t('review.time', { defaultValue: 'Time' })}:</strong> {estimate.estimated_minutes_low}–{estimate.estimated_minutes_high} {t('review.minutes', { defaultValue: 'min' })}</span>
            <span><strong>{t('review.chapters', { defaultValue: 'Chapters' })}:</strong> {estimate.chapter_count}</span>
          </div>
          <table className="text-[12px]">
            <thead className="text-muted-foreground">
              <tr className="text-left">
                <th className="py-1 pr-4 font-medium">{t('review.stage', { defaultValue: 'Stage' })}</th>
                <th className="py-1 pr-4 font-medium">{t('review.status', { defaultValue: 'Status' })}</th>
                <th className="py-1 pr-4 font-medium">{t('review.tokens', { defaultValue: 'Tokens (in/out)' })}</th>
                <th className="py-1 text-right font-medium">{t('review.usd', { defaultValue: 'USD' })}</th>
              </tr>
            </thead>
            <tbody>
              {estimate.per_stage.map((s) => (
                <tr key={s.stage} className="border-t">
                  <td className="py-1 pr-4">
                    <span className="capitalize">{s.stage}</span>
                    {s.provider_kind && (
                      <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        s.is_local
                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                          : 'bg-sky-500/15 text-sky-700 dark:text-sky-400'}`}>
                        {s.is_local
                          ? t('review.localFree', { defaultValue: '🖥 {{kind}} · free', kind: s.provider_kind })
                          : t('review.cloud', { defaultValue: '☁ {{kind}}', kind: s.provider_kind })}
                      </span>
                    )}
                  </td>
                  <td className="py-1 pr-4 text-muted-foreground">{s.status}</td>
                  <td className="py-1 pr-4 text-muted-foreground">
                    {s.input_tokens || s.output_tokens ? `${tok(s.input_tokens)} / ${tok(s.output_tokens)}` : '—'}
                  </td>
                  <td className="py-1 text-right">{s.status === 'ok' ? money(s.estimated_usd) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {estimate.notes.length > 0 && (
            <ul className="list-disc pl-5 text-[11px] text-amber-600 dark:text-amber-400">
              {estimate.notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
          <p className="text-[11px] italic text-muted-foreground">{estimate.disclaimer}</p>
        </div>
      )}

      <button type="button"
        onClick={() => launch.mutate(buildCreatePayload())}
        disabled={launch.isPending}
        className="self-start rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
        {launch.isPending
          ? t('review.launching', { defaultValue: 'Launching…' })
          : t('review.launch', { defaultValue: 'Launch campaign' })}
      </button>
    </div>
  );
}

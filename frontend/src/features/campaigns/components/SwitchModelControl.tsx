import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { campaignErrorCode } from '../api';
import { useUpdateCampaign, useResumeCampaign } from '../hooks/useCampaignMutations';
import { ModelRolePicker } from './ModelRolePicker';
import type { CampaignDetail, UpdateCampaignPayload } from '../types';

/** D-FACTORY-SWITCH-MODEL-RESUME (view + control) — on a PAUSED campaign, re-pick the
 *  translation / knowledge LLM (e.g. cloud rate-limited overnight → switch to a local
 *  model) and resume; the remaining pending/failed chapters dispatch on the new model
 *  (already-done chapters keep their version). Collapsed by default. */
export function SwitchModelControl({ campaign }: { campaign: CampaignDetail }) {
  const { t } = useTranslation('campaigns');
  const [open, setOpen] = useState(false);
  const [translationRef, setTranslationRef] = useState<string | null>(campaign.translation_model_ref);
  const [knowledgeRef, setKnowledgeRef] = useState<string | null>(campaign.knowledge_model_ref);

  const resume = useResumeCampaign({
    onSuccess: () => toast.success(t('monitor.switchedResumed', { defaultValue: 'Model switched — resuming.' })),
    onError: (e) => campaignErrorCode(e) === 'CAMPAIGN_OVER_BUDGET'
      ? toast.error(t('monitor.overBudget', { defaultValue: 'Over budget — raise the cap before resuming.' }))
      : toast.error(t('monitor.actionFailed', { defaultValue: 'Action failed: {{error}}', error: e.message })),
  });
  const update = useUpdateCampaign({
    onSuccess: (c) => resume.mutate(c.campaign_id),
    onError: (e) => toast.error(t('monitor.switchFailed', { defaultValue: 'Could not switch model: {{error}}', error: e.message })),
  });

  // user_model picks: a ref implies source 'user_model'; clearing sets both null.
  const pick = (ref: string | null): { source: string | null; ref: string | null } =>
    ({ source: ref ? 'user_model' : null, ref });

  const onSwitchAndResume = () => {
    const tr = pick(translationRef);
    const kn = pick(knowledgeRef);
    const patch: UpdateCampaignPayload = {
      translation_model_source: tr.source, translation_model_ref: tr.ref,
      knowledge_model_source: kn.source, knowledge_model_ref: kn.ref,
    };
    update.mutate({ campaignId: campaign.campaign_id, patch });
  };

  const busy = update.isPending || resume.isPending;

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="text-sm font-medium text-amber-700 hover:underline dark:text-amber-400">
        {t('monitor.switchModel', { defaultValue: 'Switch model & resume' })}
      </button>
      {open && (
        <div className="mt-3 flex flex-col gap-3">
          <p className="text-[11px] text-muted-foreground">
            {t('monitor.switchModelHint', {
              defaultValue: 'Re-pick the LLM for the remaining chapters (e.g. switch to a local model if a cloud provider is rate-limited). Already-completed chapters keep their version.',
            })}
          </p>
          <ModelRolePicker capability="chat"
            label={t('monitor.translationModel', { defaultValue: 'Translation model' })}
            value={translationRef} onChange={setTranslationRef} disabled={busy} />
          <ModelRolePicker capability="chat"
            label={t('monitor.knowledgeModel', { defaultValue: 'Knowledge model' })}
            value={knowledgeRef} onChange={setKnowledgeRef} disabled={busy} />
          <button type="button" onClick={onSwitchAndResume} disabled={busy}
            className="self-start rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
            {busy
              ? t('monitor.switching', { defaultValue: 'Switching…' })
              : t('monitor.switchModel', { defaultValue: 'Switch model & resume' })}
          </button>
        </div>
      )}
    </div>
  );
}

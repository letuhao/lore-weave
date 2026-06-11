import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { campaignErrorCode } from '../api';
import { useUpdateCampaign, useResumeCampaign } from '../hooks/useCampaignMutations';
import { ModelRolePicker } from './ModelRolePicker';
import type { CampaignDetail, UpdateCampaignPayload } from '../types';

/** The switchable LLM roles + their campaign columns. Embedding/rerank are NOT here
 *  (knowledge-project SSOT; embedding change is destructive). All are `chat` capability. */
const SWITCHABLE_ROLES = [
  { key: 'translation', srcCol: 'translation_model_source', refCol: 'translation_model_ref', labelKey: 'monitor.translationModel', labelDefault: 'Translation model' },
  { key: 'knowledge', srcCol: 'knowledge_model_source', refCol: 'knowledge_model_ref', labelKey: 'monitor.knowledgeModel', labelDefault: 'Knowledge model' },
  { key: 'verifier', srcCol: 'verifier_model_source', refCol: 'verifier_model_ref', labelKey: 'monitor.verifierModel', labelDefault: 'Verifier model (blank = follow translation)' },
  { key: 'eval_judge', srcCol: 'eval_judge_model_source', refCol: 'eval_judge_model_ref', labelKey: 'monitor.evalJudgeModel', labelDefault: 'Eval-judge model (optional)' },
] as const satisfies ReadonlyArray<{
  key: string;
  srcCol: keyof UpdateCampaignPayload;
  refCol: keyof UpdateCampaignPayload;
  labelKey: string;
  labelDefault: string;
}>;

/** D-FACTORY-SWITCH-MODEL-RESUME / D-FACTORY-SWITCH-VERIFIER-EVAL-UI (view + control) —
 *  on a PAUSED campaign, re-pick any of the four LLM roles (e.g. cloud rate-limited
 *  overnight → switch to a local model) and resume; the remaining pending/failed
 *  chapters dispatch on the new model (already-done chapters keep their version).
 *  Collapsed by default. */
export function SwitchModelControl({ campaign }: { campaign: CampaignDetail }) {
  const { t } = useTranslation('campaigns');
  const [open, setOpen] = useState(false);
  const [refs, setRefs] = useState<Record<string, string | null>>(() =>
    Object.fromEntries(SWITCHABLE_ROLES.map((r) => [r.key, campaign[r.refCol] as string | null])));

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

  const setRef = (key: string) => (ref: string | null) => setRefs((prev) => ({ ...prev, [key]: ref }));

  const onSwitchAndResume = () => {
    // For each role: a ref implies source 'user_model'; cleared sets both null (verifier
    // null → follows the translator; eval-judge null → service-wide fallback).
    const patch: Record<string, string | null> = {};
    for (const r of SWITCHABLE_ROLES) {
      const ref = refs[r.key];
      patch[r.srcCol] = ref ? 'user_model' : null;
      patch[r.refCol] = ref;
    }
    update.mutate({ campaignId: campaign.campaign_id, patch: patch as UpdateCampaignPayload });
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
          {SWITCHABLE_ROLES.map((r) => (
            <ModelRolePicker key={r.key} capability="chat"
              label={t(r.labelKey, { defaultValue: r.labelDefault })}
              value={refs[r.key]} onChange={setRef(r.key)} disabled={busy} />
          ))}
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

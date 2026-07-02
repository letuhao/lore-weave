import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker';
import { RERANK_CAPABILITY } from '../../settings/api';
import { AddModelCta } from '@/components/shared/AddModelCta';

/**
 * D-RERANK-NOT-BYOK (S0b) — Rerank model picker for knowledge projects.
 *
 * W5: now a THIN WRAPPER around the shared {@link ModelPicker}
 * (`capability=RERANK_CAPABILITY`) — the bespoke fetch effect + orphan-option
 * logic moved into the shared component. This wrapper keeps the site-specific
 * label / hint / empty-state copy (incl. the C2 discovery hint).
 *
 * Binds the project's `rerank_model` (a provider-registry `user_model_id`
 * UUID). Rerank is OPTIONAL — the "None" option clears it and raw-search
 * simply skips the cross-encoder junk-rejection step (degrades to fusion
 * order). There is NO platform fallback: with no rerank model registered, the
 * list is empty and the project runs without rerank.
 */
interface Props {
  /** The selected rerank model's `user_model_id` UUID, or null. */
  value: string | null;
  onChange: (userModelId: string | null) => void;
  disabled?: boolean;
}

export function RerankModelPicker({ value, onChange, disabled }: Props) {
  const { t } = useTranslation('knowledge');

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.form.rerankModel', { defaultValue: 'Rerank model (optional)' })}
      </span>
      <ModelPicker
        capability={RERANK_CAPABILITY}
        value={value}
        onChange={onChange}
        disabled={disabled}
        allowNone
        noneLabel={t('projects.form.rerankModelNone', {
          defaultValue: 'None (skip rerank — keep fusion order)',
        })}
        ariaLabel={t('projects.form.rerankModel', {
          defaultValue: 'Rerank model (optional)',
        })}
        emptyState={
          // C1 (BL-1): genuine zero-result (fetch resolved, no rerank models) —
          // ModelPicker only renders this after the fetch resolves empty, so a
          // pending fetch never shows a false empty. Explain the empty picker AND
          // offer the in-flow register path (C0 AddModelCta deep-links to
          // /settings/providers + carries a return) instead of a dead end.
          <span className="flex flex-col gap-1 text-[11px] text-muted-foreground">
            {t('projects.form.rerankModelEmpty', {
              defaultValue:
                'No rerank-capable models configured. Register one to enable junk-rejection.',
            })}
            <AddModelCta capability={RERANK_CAPABILITY} variant="link" />
            {/* C2 (BL-2): setup guidance for the discovery path — self-hosted rerank
                models are auto-discovered from a local-rerank (Cohere-compatible)
                credential on Refresh, no hand-tagging needed. */}
            <span className="text-muted-foreground/75">
              {t('projects.form.rerankDiscoveryHint', {
                defaultValue:
                  'Self-hosted? Add a local-rerank (Cohere-compatible) credential in AI Models, then Refresh — rerank models are auto-discovered.',
              })}
            </span>
          </span>
        }
      />
      <span className="text-[11px] text-muted-foreground">
        {t('projects.form.rerankModelHint', {
          defaultValue:
            'Cross-encoder rerank for raw-search junk-rejection. Optional — left empty, search keeps fusion order.',
        })}
      </span>
    </div>
  );
}

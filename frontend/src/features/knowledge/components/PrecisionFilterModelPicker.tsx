import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker';

/**
 * D-WX-PRECISION-FILTER-MODEL-ARCH — precision-filter model picker.
 *
 * W5: now a THIN WRAPPER around the shared {@link ModelPicker}
 * (`capability="chat"`) — the bespoke fetch effect + orphan-option logic moved
 * into the shared component. This wrapper keeps the site-specific label /
 * hint / default-option copy.
 *
 * Binds the project's `extraction_config.precision_filter.model_ref` (a
 * provider-registry `user_model_id` UUID), `model_source='user_model'`.
 *
 * The filter model was previously a HARDCODED platform env UUID of one user's
 * model, submitted scoped to the campaign's user → 404 for every other user →
 * decoupled extraction stalled. The model is now per-project, per-user, picked
 * here. The "Use extraction model (default)" option emits null — the BE
 * resolves the filter to the project's own llm_model (never a global model).
 */
interface Props {
  /** The selected filter model's `user_model_id` UUID, or null (= use extraction model). */
  value: string | null;
  onChange: (userModelId: string | null) => void;
  disabled?: boolean;
}

export function PrecisionFilterModelPicker({ value, onChange, disabled }: Props) {
  const { t } = useTranslation('knowledge');

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.extractionTuning.filterModel', { defaultValue: 'Filter model (optional)' })}
      </span>
      <ModelPicker
        capability="chat"
        value={value}
        onChange={onChange}
        disabled={disabled}
        allowNone
        noneLabel={t('projects.extractionTuning.filterModelDefault', {
          defaultValue: 'Use extraction model (default)',
        })}
        ariaLabel={t('projects.extractionTuning.filterModel', {
          defaultValue: 'Filter model (optional)',
        })}
      />
      <span className="text-[11px] text-muted-foreground">
        {t('projects.extractionTuning.filterModelHint', {
          defaultValue:
            'LLM that judges relation precision. Left as default, the filter reuses your extraction model (per-user, BYOK). Pick a stronger model for higher-precision filtering.',
        })}
      </span>
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker';

interface Props {
  /** BYOK capability to filter the user's models by ('chat' | 'embedding' | 'rerank'). */
  capability: string;
  label: string;
  /** The selected model's user_model_id, or null. */
  value: string | null;
  onChange: (userModelId: string | null) => void;
  disabled?: boolean;
  hint?: string;
}

/**
 * S5c — generalized BYOK model picker for the campaign Model Matrix. One component
 * drives all six roles (different `capability`). W5: now a thin wrapper over THE
 * shared ModelPicker (search/favorites/recents/orphan-row/none built in); the
 * per-capability fetch dedupe (D-S5C-PICKER-DEDUP) is handled by the shared
 * useUserModels module cache, so the four `chat` pickers still fetch once.
 */
export function ModelRolePicker({ capability, label, value, onChange, disabled, hint }: Props) {
  const { t } = useTranslation('campaigns');

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <ModelPicker
        capability={capability}
        value={value}
        onChange={onChange}
        disabled={disabled}
        allowNone
        noneLabel={t('matrix.none', { defaultValue: 'None' })}
        ariaLabel={label}
        emptyState={
          <span className="text-[11px] text-muted-foreground">
            {t('matrix.empty', {
              defaultValue: 'No {{capability}}-capable models. Add one in AI Models → Credentials.',
              capability,
            })}
          </span>
        }
      />
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { useByokModels } from '../hooks/useByokModels';

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
 * drives all six roles (different `capability`); mirrors the knowledge
 * EmbeddingModelPicker (native <select> bound to user_model_id, orphan-value guard,
 * empty-registry hint). View-only; the model fetch is shared per-capability via
 * useByokModels (D-S5C-PICKER-DEDUP) so the four `chat` pickers fetch once.
 */
export function ModelRolePicker({ capability, label, value, onChange, disabled, hint }: Props) {
  const { t } = useTranslation('campaigns');
  const { accessToken } = useAuth();
  const { models, loading, error } = useByokModels(capability);

  const valueInOptions =
    value === null || models.some((m) => m.user_model_id === value);

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        disabled={disabled || loading}
        className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
      >
        <option value="">
          {t('matrix.none', { defaultValue: 'None' })}
        </option>
        {!valueInOptions && value !== null && (
          <option value={value}>
            {t('matrix.orphan', { defaultValue: 'Previously selected (no longer in your registry)' })}
          </option>
        )}
        {models.map((m) => (
          <option key={m.user_model_id} value={m.user_model_id}>
            {m.alias ? `${m.alias} (${m.provider_model_name})` : `${m.provider_kind}/${m.provider_model_name}`}
          </option>
        ))}
      </select>
      {error && (
        <span className="text-[11px] text-destructive">
          {t('matrix.loadError', { defaultValue: 'Failed to load models.' })}
        </span>
      )}
      {!loading && !error && accessToken && models.length === 0 && (
        <span className="text-[11px] text-muted-foreground">
          {t('matrix.empty', {
            defaultValue: 'No {{capability}}-capable models. Add one in AI Models → Credentials.',
            capability,
          })}
        </span>
      )}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

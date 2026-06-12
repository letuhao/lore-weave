import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';

/**
 * D-WX-PRECISION-FILTER-MODEL-ARCH — precision-filter model picker.
 *
 * Mirrors {@link RerankModelPicker}: fetches the user's BYOK `capability=chat`
 * models from provider-registry and binds a `<select>` to the project's
 * `extraction_config.precision_filter.model_ref` (a provider-registry
 * `user_model_id` UUID), `model_source='user_model'`.
 *
 * The filter model was previously a HARDCODED platform env UUID of one user's
 * model, submitted scoped to the campaign's user → 404 for every other user →
 * decoupled extraction stalled. The model is now per-project, per-user, picked
 * here. Selecting `""` (default) means "use the extraction model" — the BE
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
  const { accessToken } = useAuth();
  const [models, setModels] = useState<UserModel[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) {
      setModels([]);
      return;
    }
    let cancelled = false;
    setError(null);
    aiModelsApi
      .listUserModels(accessToken, { capability: 'chat', include_inactive: false })
      .then((resp) => {
        if (cancelled) return;
        setModels(resp.items);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const loading = models === null;
  // Show the saved model truthfully even if it's no longer in the registry.
  const valueInOptions =
    value === null || (models?.some((m) => m.user_model_id === value) ?? false);

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.extractionTuning.filterModel', { defaultValue: 'Filter model (optional)' })}
      </span>
      <select
        value={value ?? ''}
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === '' ? null : v);
        }}
        disabled={disabled || loading}
        className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
      >
        <option value="">
          {t('projects.extractionTuning.filterModelDefault', {
            defaultValue: 'Use extraction model (default)',
          })}
        </option>
        {!valueInOptions && value !== null && (
          <option value={value}>
            {t('projects.extractionTuning.filterModelOrphan', {
              defaultValue: 'Previously selected model (no longer in your registry)',
            })}
          </option>
        )}
        {(models ?? []).map((m) => {
          const label = m.alias
            ? `${m.alias} (${m.provider_model_name})`
            : `${m.provider_kind}/${m.provider_model_name}`;
          return (
            <option key={m.user_model_id} value={m.user_model_id}>
              {label}
            </option>
          );
        })}
      </select>
      {loading && (
        <span className="text-[11px] text-muted-foreground">
          {t('projects.extractionTuning.filterModelLoading', { defaultValue: 'Loading models…' })}
        </span>
      )}
      {error && (
        <span className="text-[11px] text-destructive">
          {t('projects.extractionTuning.filterModelError', {
            defaultValue: 'Failed to load models.',
          })}
        </span>
      )}
      <span className="text-[11px] text-muted-foreground">
        {t('projects.extractionTuning.filterModelHint', {
          defaultValue:
            'LLM that judges relation precision. Left as default, the filter reuses your extraction model (per-user, BYOK). Pick a stronger model for higher-precision filtering.',
        })}
      </span>
    </label>
  );
}

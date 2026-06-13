import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';
import { RERANK_CAPABILITY } from '../../settings/api';
import { AddModelCta } from '@/components/shared/AddModelCta';

/**
 * D-RERANK-NOT-BYOK (S0b) — Rerank model picker for knowledge projects.
 *
 * Mirrors {@link EmbeddingModelPicker}: fetches the user's BYOK models tagged
 * `capability=rerank` from provider-registry and renders a `<select>` bound to
 * the project's `rerank_model` (a provider-registry `user_model_id` UUID).
 *
 * Rerank is OPTIONAL — selecting `""` clears it and raw-search simply skips the
 * cross-encoder junk-rejection step (degrades to fusion order). There is NO
 * platform fallback: with no rerank model registered, the list is empty and the
 * project runs without rerank.
 */
interface Props {
  /** The selected rerank model's `user_model_id` UUID, or null. */
  value: string | null;
  onChange: (userModelId: string | null) => void;
  disabled?: boolean;
}

export function RerankModelPicker({ value, onChange, disabled }: Props) {
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
      .listUserModels(accessToken, { capability: RERANK_CAPABILITY, include_inactive: false })
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
  // Surface a synthetic option when the project's saved model is no longer in
  // the registry, so the user sees the truth (same guard as EmbeddingModelPicker).
  const valueInOptions =
    value === null || (models?.some((m) => m.user_model_id === value) ?? false);

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.form.rerankModel', { defaultValue: 'Rerank model (optional)' })}
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
          {t('projects.form.rerankModelNone', {
            defaultValue: 'None (skip rerank — keep fusion order)',
          })}
        </option>
        {!valueInOptions && value !== null && (
          <option value={value}>
            {t('projects.form.rerankModelOrphan', {
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
          {t('projects.form.rerankModelLoading', { defaultValue: 'Loading rerank models…' })}
        </span>
      )}
      {error && (
        <span className="text-[11px] text-destructive">
          {t('projects.form.rerankModelError', { defaultValue: 'Failed to load rerank models.' })}
        </span>
      )}
      {!loading && !error && accessToken && (models?.length ?? 0) === 0 && (
        // C1 (BL-1): genuine zero-result (fetch resolved, no rerank models) — gated
        // on `!loading` so a pending fetch never shows a false empty. Explain the
        // empty picker AND offer the in-flow register path (C0 AddModelCta deep-links
        // to /settings/providers + carries a return) instead of a dead end.
        <span className="flex flex-col gap-1 text-[11px] text-muted-foreground">
          {t('projects.form.rerankModelEmpty', {
            defaultValue:
              'No rerank-capable models configured. Register one to enable junk-rejection.',
          })}
          <AddModelCta capability={RERANK_CAPABILITY} variant="link" />
        </span>
      )}
      <span className="text-[11px] text-muted-foreground">
        {t('projects.form.rerankModelHint', {
          defaultValue:
            'Cross-encoder rerank for raw-search junk-rejection. Optional — left empty, search keeps fusion order.',
        })}
      </span>
    </label>
  );
}

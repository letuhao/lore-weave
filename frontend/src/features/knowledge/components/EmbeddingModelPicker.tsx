import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';

/**
 * K12.4 — Embedding model picker for knowledge projects.
 *
 * Fetches the user's BYOK models tagged `capability=embedding` from
 * provider-registry and renders a `<select>` bound to the caller's
 * state. Selecting `""` clears the project's embedding_model
 * (backend treats null as "no L3 for this project").
 *
 * Why this lives in the knowledge feature rather than ai-models:
 * ai-models is the registry management page (add/remove/edit
 * credentials); knowledge/ is the consumer-side that picks WHICH
 * registered model this project uses. The picker is a small view
 * wrapper; the actual model list API stays in ai-models/api.ts.
 */
interface Props {
  value: string | null;
  onChange: (modelName: string | null) => void;
  disabled?: boolean;
}

export function EmbeddingModelPicker({ value, onChange, disabled }: Props) {
  const { t } = useTranslation('memory');
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
      .listUserModels(accessToken, { capability: 'embedding', include_inactive: false })
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
  // Guard: if the project's current `value` doesn't appear in the
  // fetched models (model deleted from registry, server-side fallback
  // name, etc.) the <select> would render no matching <option> and
  // the browser would silently show "None" — misrepresenting the
  // real state. Detect and surface a synthetic option so the user
  // sees the truth.
  const valueInOptions =
    value === null ||
    (models?.some((m) => m.provider_model_name === value) ?? false);

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">
        {t('projects.form.embeddingModel', {
          defaultValue: 'Embedding model',
        })}
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
          {t('projects.form.embeddingModelNone', {
            defaultValue: 'None (no semantic passages)',
          })}
        </option>
        {!valueInOptions && value !== null && (
          <option value={value}>
            {t('projects.form.embeddingModelOrphan', {
              defaultValue: '{{name}} (not in your registry)',
              name: value,
            })}
          </option>
        )}
        {(models ?? []).map((m) => {
          const label = m.alias
            ? `${m.alias} (${m.provider_model_name})`
            : `${m.provider_kind}/${m.provider_model_name}`;
          return (
            <option key={m.user_model_id} value={m.provider_model_name}>
              {label}
            </option>
          );
        })}
      </select>
      {loading && (
        <span className="text-[11px] text-muted-foreground">
          {t('projects.form.embeddingModelLoading', {
            defaultValue: 'Loading embedding models…',
          })}
        </span>
      )}
      {error && (
        <span className="text-[11px] text-destructive">
          {t('projects.form.embeddingModelError', {
            defaultValue: 'Failed to load embedding models.',
          })}
        </span>
      )}
      {!loading && !error && accessToken && (models?.length ?? 0) === 0 && (
        // Only show "registry empty" when we actually attempted to load
        // with a valid token. Without this gate, an unauthed render
        // (hypothetical — route guards normally prevent it) would
        // falsely tell the user to add a model.
        <span className="text-[11px] text-muted-foreground">
          {t('projects.form.embeddingModelEmpty', {
            defaultValue:
              'No embedding-capable models configured. Add one in AI Models → Credentials.',
          })}
        </span>
      )}
      <span className="text-[11px] text-muted-foreground">
        {t('projects.form.embeddingModelHint', {
          defaultValue:
            'Governs which vector space this project uses for semantic passage retrieval.',
        })}
      </span>
    </label>
  );
}

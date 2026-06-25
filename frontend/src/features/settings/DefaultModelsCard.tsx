import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { AddModelCta } from '@/components/shared/AddModelCta';
import { defaultModelsApi, RERANK_CAPABILITY, PLANNER_CAPABILITY, CHAT_CAPABILITY } from './api';

/**
 * Per-user DEFAULT model per capability (rerank/embedding). Restores the
 * default-model UX the removed RERANK_URL/_MODEL .env config gave — the BYOK way:
 * the default is one of the user's own registered models, resolved server-side by
 * provider-registry. Raw search (knowledge + the upcoming glossary search) falls
 * back to it when no per-scope model is set.
 */

interface RowProps {
  capability: string;
  /** Capability used to LIST candidate models — defaults to `capability`. Differs only
   *  for `planner`, a role with no model flag: it lists chat models but saves under
   *  `planner`. */
  listCapability?: string;
  label: string;
  hint: string;
  value: string | null;
  onChange: (userModelId: string | null) => void;
  disabled?: boolean;
}

function DefaultModelRow({ capability, listCapability, label, hint, value, onChange, disabled }: RowProps) {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [models, setModels] = useState<UserModel[] | null>(null);
  const fetchCapability = listCapability ?? capability;

  useEffect(() => {
    if (!accessToken) {
      setModels([]);
      return;
    }
    let cancelled = false;
    aiModelsApi
      .listUserModels(accessToken, { capability: fetchCapability, include_inactive: false })
      .then((r) => {
        if (!cancelled) setModels(r.items);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, fetchCapability]);

  const loading = models === null;
  // Show the saved value even if it's no longer in the registry, so the user sees
  // the truth (mirrors RerankModelPicker).
  const valueInOptions = value === null || (models?.some((m) => m.user_model_id === value) ?? false);

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium">{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        disabled={disabled || loading}
        className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
      >
        <option value="">{t('defaultModels.none', { defaultValue: 'None' })}</option>
        {!valueInOptions && value !== null && (
          <option value={value}>
            {t('defaultModels.orphan', { defaultValue: 'Previously selected model (no longer in your registry)' })}
          </option>
        )}
        {(models ?? []).map((m) => {
          const optLabel = m.alias
            ? `${m.alias} (${m.provider_model_name})`
            : `${m.provider_kind}/${m.provider_model_name}`;
          return (
            <option key={m.user_model_id} value={m.user_model_id}>
              {optLabel}
            </option>
          );
        })}
      </select>
      {!loading && (models?.length ?? 0) === 0 && (
        <span className="flex flex-col gap-1 text-[11px] text-muted-foreground">
          {t('defaultModels.empty', { defaultValue: 'No capable models configured.' })}
          <AddModelCta capability={fetchCapability} variant="link" />
        </span>
      )}
      <span className="text-[11px] text-muted-foreground">{hint}</span>
    </label>
  );
}

export function DefaultModelsCard() {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    defaultModelsApi
      .get(accessToken)
      .then((r) => {
        if (!cancelled) setDefaults(r.defaults || {});
      })
      .catch(() => {
        /* best-effort load; an empty card still works */
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const save = async (capability: string, userModelId: string | null) => {
    if (!accessToken) return;
    const prev = defaults;
    // Optimistic update.
    setDefaults((d) => {
      const next = { ...d };
      if (userModelId) next[capability] = userModelId;
      else delete next[capability];
      return next;
    });
    setSaving(true);
    try {
      await defaultModelsApi.set(accessToken, capability, userModelId);
      toast.success(t('defaultModels.saved', { defaultValue: 'Default updated' }));
    } catch (e) {
      setDefaults(prev); // rollback
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-4 rounded-lg border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold">
          {t('defaultModels.heading', { defaultValue: 'Default models' })}
        </h3>
        <p className="text-xs text-muted-foreground">
          {t('defaultModels.subtitle', {
            defaultValue: 'Your per-user fallback models (BYOK — your own). Used when no per-scope model is set.',
          })}
        </p>
      </div>
      <div className="max-w-sm">
        {/* Embedding default is intentionally NOT exposed yet: a query-time embedding
            default would break retrieval (it must match the model the project was
            indexed with), and the index-time consumer is a separate follow-up. The
            BE storage/routes stay generic (rerank+embedding) and ready. */}
        <DefaultModelRow
          capability={RERANK_CAPABILITY}
          label={t('defaultModels.rerank', { defaultValue: 'Default reranker' })}
          hint={t('defaultModels.rerankHint', {
            defaultValue: 'Cross-encoder rerank for raw-search junk-rejection. Optional — applies when a project has no rerank model set.',
          })}
          value={defaults[RERANK_CAPABILITY] ?? null}
          onChange={(id) => void save(RERANK_CAPABILITY, id)}
          disabled={saving}
        />
        {/* Planner default (D-PLAN-PLANNER-DEFAULT-FE): the model the glossary AI plans
            with. Lists chat models (planner is a role, not a model flag); pin a STRONG
            one so the planner isn't stuck on an arbitrary/weak fallback. */}
        <div className="mt-4">
          <DefaultModelRow
            capability={PLANNER_CAPABILITY}
            listCapability={CHAT_CAPABILITY}
            label={t('defaultModels.planner', { defaultValue: 'Default planner' })}
            hint={t('defaultModels.plannerHint', {
              defaultValue: 'The chat model the glossary assistant uses to build multi-step plans. Pick a strong, tool-capable model — otherwise planning falls back to an arbitrary chat model and often fails.',
            })}
            value={defaults[PLANNER_CAPABILITY] ?? null}
            onChange={(id) => void save(PLANNER_CAPABILITY, id)}
            disabled={saving}
          />
        </div>
      </div>
    </div>
  );
}

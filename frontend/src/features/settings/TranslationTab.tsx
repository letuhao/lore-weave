import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Save, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { translationApi, type UserTranslationPreferences, type ModelSource } from '@/features/translation/api';
import { LanguagePicker } from '@/components/shared/LanguagePicker';
import { TRANSLATION_TARGETS } from '@/lib/languages';
import { providerApi, type ProviderCredential, type UserModel } from './api';

export function TranslationTab() {
  const { t } = useTranslation('settings');
  const { accessToken } = useAuth();
  const [prefs, setPrefs] = useState<UserTranslationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Model selection
  const [providers, setProviders] = useState<ProviderCredential[]>([]);
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);
  // S3: a providers/models fetch FAILURE must not masquerade as "you have no models" (the
  // benign empty state) — track it so the picker shows a load error + Retry instead.
  const [modelsError, setModelsError] = useState(false);
  const [modelsReload, setModelsReload] = useState(0);

  // Form state
  const [targetLang, setTargetLang] = useState('en');
  const [modelSource, setModelSource] = useState<ModelSource>('user_model');
  const [modelRef, setModelRef] = useState<string>('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [userPromptTpl, setUserPromptTpl] = useState('');

  // Load preferences
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    translationApi.getPreferences(accessToken).then((p) => {
      if (cancelled) return;
      setPrefs(p);
      setTargetLang(p.target_language);
      setModelSource(p.model_source);
      setModelRef(p.model_ref ?? '');
      setSystemPrompt(p.system_prompt);
      setUserPromptTpl(p.user_prompt_tpl);
    }).catch(() => {
      if (!cancelled) toast.error(t('translation.toast.load_failed'));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [accessToken]);

  // Load providers + user models for model picker
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setModelsError(false);
    setLoadingModels(true);
    Promise.all([
      providerApi.listProviders(accessToken),
      providerApi.listUserModels(accessToken),
    ]).then(([p, m]) => {
      if (cancelled) return;
      setProviders(p.items ?? []);
      setUserModels((m.items ?? []).filter((model) => model.is_active));
    }).catch(() => {
      // S3: surface the failure rather than swallowing it into the "no models" state.
      if (!cancelled) setModelsError(true);
    }).finally(() => {
      if (!cancelled) setLoadingModels(false);
    });
    return () => { cancelled = true; };
  }, [accessToken, modelsReload]);

  // Group models by provider
  const modelsByProvider = new Map<string, UserModel[]>();
  for (const m of userModels) {
    const key = m.provider_credential_id;
    if (!modelsByProvider.has(key)) modelsByProvider.set(key, []);
    modelsByProvider.get(key)!.push(m);
  }

  async function handleSave() {
    if (!accessToken) return;

    // Validate user_prompt_tpl contains {chapter_text}
    if (!userPromptTpl.includes('{chapter_text}')) {
      toast.error(t('translation.toast.tpl_needs_chapter'));
      return;
    }

    setSaving(true);
    try {
      const updated = await translationApi.putPreferences(accessToken, {
        target_language: targetLang,
        model_source: modelSource,
        model_ref: modelRef || null,
        system_prompt: systemPrompt,
        user_prompt_tpl: userPromptTpl,
      });
      setPrefs(updated);
      toast.success(t('translation.toast.saved'));
    } catch (e) {
      toast.error((e as Error).message || t('translation.toast.save_failed'));
    } finally {
      setSaving(false);
    }
  }

  const isDirty = prefs && (
    targetLang !== prefs.target_language ||
    modelSource !== prefs.model_source ||
    modelRef !== (prefs.model_ref ?? '') ||
    systemPrompt !== prefs.system_prompt ||
    userPromptTpl !== prefs.user_prompt_tpl
  );

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-12 animate-pulse rounded-md bg-card" />
        ))}
      </div>
    );
  }

  const selectedModel = userModels.find((m) => m.user_model_id === modelRef);

  return (
    <div>
      <div className="border-b py-5">
        <h2 className="text-sm font-semibold">{t('translation.heading')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('translation.subtitle')}</p>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium">{t('translation.target_lang')}</label>
            {/* D13: the default-language picker is the SAME closed registry (TRANSLATION_TARGETS)
                the backend accepts, not a private 8-code literal that silently drifts from the SSOT.
                LanguagePicker's orphan guard keeps a legacy stored value visible. */}
            <LanguagePicker
              value={targetLang}
              onChange={setTargetLang}
              codes={TRANSLATION_TARGETS.map((l) => l.code)}
              aria-label={t('translation.target_lang_aria')}
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">{t('translation.default_model')}</label>
            {loadingModels ? (
              <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-3 text-[13px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> {t('translation.loading_models')}
              </div>
            ) : modelsError ? (
              <div role="alert" data-testid="settings-models-error" className="flex items-center justify-between gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                <span>{t('translation.models_load_failed', { defaultValue: "Couldn't load your models. The provider service may be unavailable." })}</span>
                <button
                  type="button"
                  onClick={() => setModelsReload((n) => n + 1)}
                  className="rounded-md border border-destructive/40 px-2 py-1 font-medium hover:bg-destructive/10"
                >
                  {t('translation.retry', { defaultValue: 'Retry' })}
                </button>
              </div>
            ) : userModels.length === 0 ? (
              <div className="rounded-md border border-dashed bg-background px-3 py-2 text-xs text-muted-foreground">
                {t('translation.no_models')}
              </div>
            ) : (
              <select
                value={modelRef}
                onChange={(e) => {
                  const model = userModels.find((m) => m.user_model_id === e.target.value);
                  setModelRef(e.target.value);
                  if (model) setModelSource('user_model');
                }}
                aria-label={t('translation.model_aria')}
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              >
                <option value="">{t('translation.select_model')}</option>
                {Array.from(modelsByProvider.entries()).map(([provId, models]) => {
                  const prov = providers.find((p) => p.provider_credential_id === provId);
                  return (
                    <optgroup key={provId} label={prov?.display_name ?? provId.slice(0, 8)}>
                      {models.map((m) => (
                        <option key={m.user_model_id} value={m.user_model_id}>
                          {m.alias || m.provider_model_name}
                        </option>
                      ))}
                    </optgroup>
                  );
                })}
              </select>
            )}
            {selectedModel && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                {selectedModel.provider_kind} — <span className="font-mono">{selectedModel.provider_model_name}</span>
              </p>
            )}
          </div>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium">{t('translation.system_prompt_tpl')}</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={4}
            placeholder={t('translation.system_prompt_ph')}
            aria-label={t('translation.system_prompt_tpl')}
            className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            {t('translation.variables')} {'{source_language}'}, {'{target_language}'}, {'{book_title}'}, {'{glossary_context}'}
          </p>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium">{t('translation.user_prompt_tpl')}</label>
          <textarea
            value={userPromptTpl}
            onChange={(e) => setUserPromptTpl(e.target.value)}
            rows={3}
            placeholder={t('translation.user_prompt_ph')}
            aria-label={t('translation.user_prompt_tpl')}
            className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            {t('translation.must_contain')} {t('translation.variables')} {'{chapter_text}'}, {'{target_language}'}, {'{source_language}'}
          </p>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            {saving ? t('translation.saving') : t('translation.save_defaults')}
          </button>
        </div>
      </div>
    </div>
  );
}

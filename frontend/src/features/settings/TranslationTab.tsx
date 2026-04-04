import { useEffect, useState } from 'react';
import { Save, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { translationApi, type UserTranslationPreferences, type ModelSource } from '@/features/translation/api';
import { providerApi, type ProviderCredential, type UserModel } from './api';

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'vi', label: 'Tiếng Việt' },
  { code: 'ja', label: '日本語' },
  { code: 'zh-TW', label: '繁體中文' },
  { code: 'ko', label: '한국어' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
];

export function TranslationTab() {
  const { accessToken } = useAuth();
  const [prefs, setPrefs] = useState<UserTranslationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Model selection
  const [providers, setProviders] = useState<ProviderCredential[]>([]);
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);

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
      if (!cancelled) toast.error('Failed to load translation preferences');
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [accessToken]);

  // Load providers + user models for model picker
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    Promise.all([
      providerApi.listProviders(accessToken),
      providerApi.listUserModels(accessToken),
    ]).then(([p, m]) => {
      if (cancelled) return;
      setProviders(p.items ?? []);
      setUserModels((m.items ?? []).filter((model) => model.is_active));
    }).catch(() => {}).finally(() => {
      if (!cancelled) setLoadingModels(false);
    });
    return () => { cancelled = true; };
  }, [accessToken]);

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
      toast.error('User prompt template must contain {chapter_text}');
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
      toast.success('Translation defaults saved');
    } catch (e) {
      toast.error((e as Error).message || 'Failed to save translation preferences');
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
        <h2 className="text-sm font-semibold">Translation Defaults</h2>
        <p className="mb-4 text-xs text-muted-foreground">Default settings for new translation jobs.</p>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium">Default Target Language</label>
            <select
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              aria-label="Default target language"
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label} ({l.code})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">Default Model</label>
            {loadingModels ? (
              <div className="flex h-9 items-center gap-2 rounded-md border bg-background px-3 text-[13px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading models...
              </div>
            ) : userModels.length === 0 ? (
              <div className="rounded-md border border-dashed bg-background px-3 py-2 text-xs text-muted-foreground">
                No models configured. Add models in the <strong>Model Providers</strong> tab first.
              </div>
            ) : (
              <select
                value={modelRef}
                onChange={(e) => {
                  const model = userModels.find((m) => m.user_model_id === e.target.value);
                  setModelRef(e.target.value);
                  if (model) setModelSource('user_model');
                }}
                aria-label="Default translation model"
                className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
              >
                <option value="">— Select a model —</option>
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
          <label className="mb-1 block text-xs font-medium">System Prompt Template</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={4}
            placeholder="You are a professional {source_language}-to-{target_language} translator..."
            aria-label="System prompt template"
            className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            Variables: {'{source_language}'}, {'{target_language}'}, {'{book_title}'}, {'{glossary_context}'}
          </p>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-medium">User Prompt Template</label>
          <textarea
            value={userPromptTpl}
            onChange={(e) => setUserPromptTpl(e.target.value)}
            rows={3}
            placeholder={'Translate the following text to {target_language}:\n\n{chapter_text}'}
            aria-label="User prompt template"
            className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            Must contain {'{chapter_text}'}. Variables: {'{chapter_text}'}, {'{target_language}'}, {'{source_language}'}
          </p>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            {saving ? 'Saving...' : 'Save Defaults'}
          </button>
        </div>
      </div>
    </div>
  );
}

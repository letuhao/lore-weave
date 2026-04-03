import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { translationApi, type UserTranslationPreferences } from '@/features/translation/api';

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

  // Form state
  const [targetLang, setTargetLang] = useState('en');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [userPromptTpl, setUserPromptTpl] = useState('');

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    translationApi.getPreferences(accessToken).then((p) => {
      if (cancelled) return;
      setPrefs(p);
      setTargetLang(p.target_language);
      setSystemPrompt(p.system_prompt);
      setUserPromptTpl(p.user_prompt_tpl);
    }).catch(() => {
      if (!cancelled) toast.error('Failed to load translation preferences');
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [accessToken]);

  async function handleSave() {
    if (!accessToken) return;
    setSaving(true);
    try {
      const updated = await translationApi.putPreferences(accessToken, {
        target_language: targetLang,
        system_prompt: systemPrompt,
        user_prompt_tpl: userPromptTpl,
      });
      setPrefs(updated);
      toast.success('Translation defaults saved');
    } catch {
      toast.error('Failed to save translation preferences');
    } finally {
      setSaving(false);
    }
  }

  const isDirty = prefs && (
    targetLang !== prefs.target_language ||
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
            <label className="mb-1 block text-xs font-medium">Model</label>
            <input
              type="text"
              value={prefs?.model_ref ?? '—'}
              disabled
              className="h-9 w-full rounded-md border bg-background px-3 text-[13px] text-muted-foreground"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">Change model in Providers tab</p>
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
            placeholder="Translate the following text to {target_language}:&#10;&#10;{text}"
            aria-label="User prompt template"
            className="w-full resize-y rounded-md border bg-background px-3 py-2 text-xs leading-relaxed focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
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

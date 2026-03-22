import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { ModelSelector } from '@/components/translation/ModelSelector';
import { PromptEditor } from '@/components/translation/PromptEditor';
import { translationApi, type UserTranslationPreferences, type ModelSource } from '@/features/translation/api';

type FormState = {
  target_language: string;
  model_source: ModelSource;
  model_ref: string | null;
  system_prompt: string;
  user_prompt_tpl: string;
};

function prefsToForm(p: UserTranslationPreferences): FormState {
  return {
    target_language: p.target_language,
    model_source: p.model_source,
    model_ref: p.model_ref,
    system_prompt: p.system_prompt,
    user_prompt_tpl: p.user_prompt_tpl,
  };
}

export function TranslationSection() {
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    translationApi.getPreferences(token)
      .then((p) => setForm(prefsToForm(p)))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSave() {
    if (!form) return;
    if (!form.model_ref) {
      setErrorMsg('Please select a model before saving.');
      return;
    }
    if (!form.user_prompt_tpl.includes('{chapter_text}')) {
      setErrorMsg('User prompt template must contain {chapter_text}.');
      return;
    }
    setSaving(true);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      await translationApi.putPreferences(token, {
        target_language: form.target_language,
        model_source: form.model_source,
        model_ref: form.model_ref,
        system_prompt: form.system_prompt,
        user_prompt_tpl: form.user_prompt_tpl,
      });
      setSuccessMsg('Defaults saved');
    } catch (e: unknown) {
      setErrorMsg((e as { message?: string })?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Translation</h2>
        <p className="text-sm text-muted-foreground">
          These defaults apply to all books unless overridden from a book's translation page.
        </p>
      </div>

      <section className="space-y-4 rounded border p-4">
        <h3 className="font-medium">Default translation settings</h3>

        {loading && (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        )}

        {!loading && form && (
          <div className="space-y-4">
            <LanguagePicker
              label="Default target language"
              value={form.target_language}
              onChange={(v) => setForm({ ...form, target_language: v })}
            />
            <ModelSelector
              token={token}
              label="Default model"
              value={{ model_source: form.model_source, model_ref: form.model_ref }}
              onChange={(v) => setForm({ ...form, model_source: v.model_source, model_ref: v.model_ref })}
              disabled={saving}
            />
            <PromptEditor
              systemPrompt={form.system_prompt}
              userPromptTpl={form.user_prompt_tpl}
              onSystemPromptChange={(v) => setForm({ ...form, system_prompt: v })}
              onUserPromptTplChange={(v) => setForm({ ...form, user_prompt_tpl: v })}
              disabled={saving}
            />

            {errorMsg && (
              <Alert variant="destructive">
                <AlertDescription>{errorMsg}</AlertDescription>
              </Alert>
            )}
            {successMsg && (
              <p className="text-sm text-green-600">{successMsg}</p>
            )}

            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save defaults'}
            </Button>
          </div>
        )}
      </section>

      <section className="rounded border p-4 text-sm text-muted-foreground">
        Per-book settings can be configured from within each book's Translation page.
      </section>
    </div>
  );
}

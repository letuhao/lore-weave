import { useState } from 'react';
import type { BookTranslationSettings, ModelSource } from '@/features/translation/api';
import { translationApi } from '@/features/translation/api';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { ModelSelector } from './ModelSelector';
import { PromptEditor } from './PromptEditor';
import { AdvancedTranslationSettings } from './AdvancedTranslationSettings';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';

type FormState = {
  target_language: string;
  model_source: ModelSource;
  model_ref: string | null;
  system_prompt: string;
  user_prompt_tpl: string;
  compact_model_source: ModelSource | null;
  compact_model_ref: string | null;
  chunk_size_tokens: number;
  invoke_timeout_secs: number;
};

function settingsToForm(s: BookTranslationSettings): FormState {
  return {
    target_language:      s.target_language,
    model_source:         s.model_source,
    model_ref:            s.model_ref,
    system_prompt:        s.system_prompt,
    user_prompt_tpl:      s.user_prompt_tpl,
    compact_model_source: s.compact_model_source,
    compact_model_ref:    s.compact_model_ref,
    chunk_size_tokens:    s.chunk_size_tokens ?? 2000,
    invoke_timeout_secs:  s.invoke_timeout_secs ?? 300,
  };
}

type Props = {
  token: string;
  bookId: string;
  settings: BookTranslationSettings;
  onClose: () => void;
  onSaved: (updated: BookTranslationSettings) => void;
};

export function SettingsDrawer({ token, bookId, settings, onClose, onSaved }: Props) {
  const [form, setForm] = useState<FormState>(settingsToForm(settings));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  async function handleSave() {
    if (!form.model_ref) { setError('Please select a model.'); return; }
    if (!form.user_prompt_tpl.includes('{chapter_text}')) {
      setError('User prompt template must contain {chapter_text}.'); return;
    }
    setSaving(true); setError(''); setSuccess('');
    try {
      const saved = await translationApi.putBookSettings(token, bookId, form);
      onSaved(saved);
      setSuccess('Saved');
    } catch (e) {
      setError((e as Error).message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    const prefs = await translationApi.getPreferences(token);
    setForm(settingsToForm({ ...prefs, book_id: bookId, owner_user_id: prefs.user_id, is_default: true }));
    setSuccess(''); setError('');
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      {/* Panel */}
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col border-l bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="font-semibold">Translation settings</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {settings.is_default && (
            <p className="text-xs text-muted-foreground rounded border p-2">
              Using your default settings. Save to override for this book.
            </p>
          )}
          <LanguagePicker
            label="Target language"
            value={form.target_language}
            onChange={(v) => setForm({ ...form, target_language: v })}
          />
          <ModelSelector
            token={token}
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
          <AdvancedTranslationSettings
            token={token}
            value={{
              compact_model_source: form.compact_model_source,
              compact_model_ref:    form.compact_model_ref,
              chunk_size_tokens:    form.chunk_size_tokens,
              invoke_timeout_secs:  form.invoke_timeout_secs,
            }}
            onChange={(v) => setForm({ ...form, ...v })}
            disabled={saving}
          />
          {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
          {success && <p className="text-sm text-green-600">{success}</p>}
        </div>
        <div className="flex gap-2 border-t p-4">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save for this book'}
          </Button>
          <Button variant="outline" onClick={handleReset} disabled={saving}>
            Reset to defaults
          </Button>
        </div>
      </div>
    </>
  );
}

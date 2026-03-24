import { useState } from 'react';
import type { Confidence } from '../types';

// Common BCP-47 language codes offered in the picker.
const COMMON_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: 'Chinese' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'ru', label: 'Russian' },
  { code: 'vi', label: 'Vietnamese' },
  { code: 'th', label: 'Thai' },
  { code: 'id', label: 'Indonesian' },
];

const CONFIDENCE_OPTIONS: { value: Confidence; label: string }[] = [
  { value: 'draft', label: 'Draft' },
  { value: 'verified', label: 'Verified' },
  { value: 'machine', label: 'Machine' },
];

type Props = {
  usedLanguages: string[];
  onAdd: (languageCode: string, value: string, confidence: Confidence) => Promise<void>;
  onClose: () => void;
};

export function AddTranslationModal({ usedLanguages, onAdd, onClose }: Props) {
  const usedSet = new Set(usedLanguages);
  const available = COMMON_LANGUAGES.filter((l) => !usedSet.has(l.code));

  const [langCode, setLangCode] = useState('');
  const [customLang, setCustomLang] = useState('');
  const [value, setValue] = useState('');
  const [confidence, setConfidence] = useState<Confidence>('draft');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const effectiveLang = langCode === '__custom__' ? customLang.trim() : langCode;

  async function handleSubmit() {
    if (!effectiveLang) return;
    setSaving(true);
    setError('');
    try {
      await onAdd(effectiveLang, value, confidence);
      onClose();
    } catch (e: unknown) {
      const msg = (e as Error).message || 'Failed to add translation';
      if (msg.includes('GLOSS_DUPLICATE_TRANSLATION_LANGUAGE')) {
        setError('A translation for this language already exists.');
      } else {
        setError(msg);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {/* Backdrop — z-[60] sits above EntityDetailPanel (z-50) */}
      <div
        className="fixed inset-0 z-[60] bg-black/30"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Dialog */}
      <div className="fixed left-1/2 top-1/2 z-[61] w-80 -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-4 shadow-xl">
        <h3 className="mb-3 text-sm font-semibold">Add Translation</h3>

        <div className="space-y-2">
          {/* Language picker */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Language</label>
            <select
              value={langCode}
              onChange={(e) => setLangCode(e.target.value)}
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="">Select language…</option>
              {available.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label} ({l.code})
                </option>
              ))}
              <option value="__custom__">Other…</option>
            </select>
          </div>

          {langCode === '__custom__' && (
            <input
              type="text"
              value={customLang}
              onChange={(e) => setCustomLang(e.target.value)}
              placeholder="BCP-47 code, e.g. ar, he, fil"
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          )}

          {/* Value */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Translation</label>
            <textarea
              value={value}
              onChange={(e) => setValue(e.target.value)}
              rows={3}
              className="w-full resize-y rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Confidence */}
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Confidence</label>
            <select
              value={confidence}
              onChange={(e) => setConfidence(e.target.value as Confidence)}
              className="w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {CONFIDENCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <div className="mt-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded border px-3 py-1 text-sm text-muted-foreground hover:bg-muted"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!effectiveLang || saving}
            className="rounded border px-3 py-1 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            {saving ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
    </>
  );
}

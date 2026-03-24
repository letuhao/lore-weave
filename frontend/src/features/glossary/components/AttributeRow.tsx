import { useEffect, useRef, useState } from 'react';
import { glossaryApi } from '../api';
import type { AttributeValue, Confidence } from '../types';
import { AttributeValueInput } from './AttributeValueInput';
import { TranslationList } from './TranslationList';

// Common BCP-47 codes for original language picker.
const LANG_OPTIONS = [
  { code: 'zh', label: 'Chinese (zh)' },
  { code: 'en', label: 'English (en)' },
  { code: 'ja', label: 'Japanese (ja)' },
  { code: 'ko', label: 'Korean (ko)' },
  { code: 'vi', label: 'Vietnamese (vi)' },
  { code: 'th', label: 'Thai (th)' },
];

type Props = {
  av: AttributeValue;
  bookId: string;
  entityId: string;
  token: string;
  onRefresh: () => void;
};

export function AttributeRow({ av, bookId, entityId, token, onRefresh }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [localValue, setLocalValue] = useState(av.original_value);
  const [localLang, setLocalLang] = useState(av.original_language);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  // True while any value/lang input inside this row has focus — prevents
  // an onRefresh-triggered prop change from overwriting in-progress edits.
  const isEditingRef = useRef(false);

  // Sync local state when the entity is refreshed from outside, but only
  // when the user is not actively editing (to avoid discarding in-progress text).
  useEffect(() => {
    if (!isEditingRef.current) {
      setLocalValue(av.original_value);
      setLocalLang(av.original_language);
    }
  }, [av.original_value, av.original_language]);

  async function saveValue(value: string, lang: string) {
    const changes: { original_value?: string; original_language?: string } = {};
    if (value !== av.original_value) changes.original_value = value;
    if (lang !== av.original_language) changes.original_language = lang;
    if (Object.keys(changes).length === 0) return;

    setIsSaving(true);
    setError('');
    try {
      await glossaryApi.patchAttributeValue(bookId, entityId, av.attr_value_id, changes, token);
      onRefresh();
    } catch (e: unknown) {
      setError((e as Error).message || 'Save failed');
    } finally {
      setIsSaving(false);
    }
  }

  async function handleAddTranslation(languageCode: string, value: string, confidence: Confidence) {
    await glossaryApi.createTranslation(bookId, entityId, av.attr_value_id, { language_code: languageCode, value, confidence }, token);
    onRefresh();
  }

  async function handleDeleteTranslation(translationId: string) {
    await glossaryApi.deleteTranslation(bookId, entityId, av.attr_value_id, translationId, token);
    onRefresh();
  }

  const translationCount = av.translations.length;
  const isRequired = av.attribute_def.is_required;

  // Value preview: truncate long values
  const preview = localValue.length > 60 ? localValue.slice(0, 60) + '…' : localValue;

  return (
    <div className="border-b last:border-b-0">
      {/* ── Collapsed header ────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-0 py-2 text-left text-xs hover:bg-muted/30"
      >
        <span className="shrink-0 text-muted-foreground">{isExpanded ? '▾' : '▸'}</span>
        <span className="w-28 shrink-0 font-medium">
          {av.attribute_def.name}
          {isRequired && <span className="ml-0.5 text-destructive">*</span>}
        </span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">{preview || '—'}</span>
        {translationCount > 0 && (
          <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-xs font-medium">
            {translationCount}
          </span>
        )}
      </button>

      {/* ── Expanded body ────────────────────────────────────────────────────── */}
      {isExpanded && (
        <div className="space-y-3 pb-3 pl-6 pr-1">
          {/* Original language */}
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Original language</label>
            <select
              value={localLang}
              onChange={(e) => setLocalLang(e.target.value)}
              onFocus={() => { isEditingRef.current = true; }}
              onBlur={() => { isEditingRef.current = false; saveValue(localValue, localLang); }}
              disabled={isSaving}
              className="rounded border bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
            >
              {LANG_OPTIONS.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
              {/* Show current value if not in the preset list */}
              {!LANG_OPTIONS.find((l) => l.code === localLang) && (
                <option value={localLang}>{localLang}</option>
              )}
            </select>
          </div>

          {/* Original value */}
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">
              Original value
              {isSaving && <span className="ml-2 text-muted-foreground">Saving…</span>}
            </label>
            <AttributeValueInput
              fieldType={av.attribute_def.field_type}
              options={av.attribute_def.options}
              value={localValue}
              onChange={setLocalValue}
              onFocus={() => { isEditingRef.current = true; }}
              onBlur={() => { isEditingRef.current = false; saveValue(localValue, localLang); }}
              disabled={isSaving}
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          {/* Translations */}
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Translations ({translationCount})
            </p>
            <TranslationList
              translations={av.translations}
              onAdd={handleAddTranslation}
              onDelete={handleDeleteTranslation}
            />
          </div>

          {/* Evidences placeholder — SP-5 */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Evidences ({av.evidences.length}) — editing in SP-5
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

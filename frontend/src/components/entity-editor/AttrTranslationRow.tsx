import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Loader2, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { ConfirmDialog } from '@/components/shared';
import type { Translation, Confidence } from '@/features/glossary/types';
import { getLanguageName } from '@/lib/languages';

const CONFIDENCE_STYLES: Record<Confidence, string> = {
  verified: 'bg-green-500/15 text-green-400',
  draft: 'bg-amber-400/15 text-amber-400',
  machine: 'bg-blue-500/15 text-blue-400',
};

interface AttrTranslationRowProps {
  bookId: string;
  entityId: string;
  attrValueId: string;
  language: string;
  translation: Translation | undefined;
  translationHint?: string | null;
  sourceOriginal?: string;
  sourceOriginalLang?: string;
  /** The owning attribute's `code`. ONLY the `aliases` attribute stores its per-language
   *  set as a JSON array string (matching the BE writer glossary_propose_aliases and the
   *  aliases-scoped reader composePerLanguageAliases) → edited here as chips. Every other
   *  tags attribute (members/participants/tropes/…) keeps CSV at its source, so its
   *  translation stays on the plain textarea to avoid source/translation format drift. */
  attrCode?: string;
  onChanged: (updated: Translation | null) => void;
}

/** Per-language alias sets are stored as a JSON array STRING (S6). Parse to chips
 *  (deduped, mirroring the BE dedupStrings); return null for a non-array value so the row
 *  falls back to the raw textarea and never silently drops a legacy/hand-edited value.
 *  Empty → []. */
function aliasTagsFromValue(value: string): string[] | null {
  const trimmed = value.trim();
  if (trimmed === '') return [];
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'string')) {
      return Array.from(new Set(parsed as string[]));
    }
  } catch {
    // not JSON → fall through to the textarea fallback
  }
  return null;
}

export function AttrTranslationRow({
  bookId, entityId, attrValueId, language,
  translation, translationHint, sourceOriginal, sourceOriginalLang, attrCode, onChanged,
}: AttrTranslationRowProps) {
  const { t } = useTranslation('entityEditor');
  const { accessToken } = useAuth();
  const [value, setValue] = useState(translation?.value ?? '');

  useEffect(() => {
    setValue(translation?.value ?? '');
  }, [translation?.translation_id, translation?.value]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isDirty = value !== (translation?.value ?? '');
  const isEmpty = !value.trim();
  // Only the `aliases` attribute stores its set as a JSON array string → render chips.
  const aliasTags = attrCode === 'aliases' ? aliasTagsFromValue(value) : null;

  const handleSave = async () => {
    if (!accessToken || isEmpty) return;
    setSaving(true);
    try {
      if (translation) {
        // Update existing
        const updated = await glossaryApi.patchTranslation(
          bookId, entityId, attrValueId, translation.translation_id,
          { value },
          accessToken,
        );
        onChanged(updated);
        toast.success(t('translation_row.toast.updated'));
      } else {
        // Create new
        const created = await glossaryApi.createTranslation(
          bookId, entityId, attrValueId,
          { language_code: language, value, confidence: 'draft' },
          accessToken,
        );
        onChanged(created);
        toast.success(t('translation_row.toast.created'));
      }
    } catch (e) {
      toast.error((e as Error).message);
    }
    setSaving(false);
  };

  const handleDelete = async () => {
    if (!accessToken || !translation) return;
    setDeleting(true);
    try {
      await glossaryApi.deleteTranslation(
        bookId, entityId, attrValueId, translation.translation_id,
        accessToken,
      );
      setValue('');
      setConfirmDelete(false);
      onChanged(null);
      toast.success(t('translation_row.toast.deleted'));
    } catch (e) {
      toast.error((e as Error).message);
    }
    setDeleting(false);
  };

  const handleConfidenceChange = async (confidence: Confidence) => {
    if (!accessToken || !translation) return;
    try {
      const updated = await glossaryApi.patchTranslation(
        bookId, entityId, attrValueId, translation.translation_id,
        { confidence },
        accessToken,
      );
      onChanged(updated);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="border-t border-dashed px-3.5 py-2 space-y-1.5" style={{ background: 'rgba(59,130,246,0.03)' }}>
      <div className="flex items-center gap-2">
        <span className="rounded bg-blue-500/12 px-1.5 py-0.5 text-[9px] font-semibold text-blue-400 uppercase">
          {language}
        </span>
        {translation && (
          <select
            value={translation.confidence}
            onChange={(e) => void handleConfidenceChange(e.target.value as Confidence)}
            className={`rounded border px-1.5 py-0.5 text-[9px] font-medium focus:outline-none ${CONFIDENCE_STYLES[translation.confidence]}`}
            aria-label={t('translation_row.confidence_aria')}
          >
            <option value="draft">{t('translation_row.confidence.draft')}</option>
            <option value="verified">{t('translation_row.confidence.verified')}</option>
            <option value="machine">{t('translation_row.confidence.machine')}</option>
          </select>
        )}
        {translation?.translator && (
          <span className="text-[9px] text-muted-foreground">{t('translation_row.by', { name: translation.translator })}</span>
        )}
        <span className="flex-1" />
        {isDirty && (
          <>
            <button
              type="button"
              onClick={() => setValue(translation?.value ?? '')}
              className="p-0.5 text-muted-foreground hover:text-foreground transition-colors"
              title={t('translation_row.discard_aria')}
            >
              <X className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving || isEmpty}
              className="inline-flex items-center gap-1 rounded bg-primary px-2 py-0.5 text-[9px] font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Check className="h-2.5 w-2.5" />}
              {t('translation_row.save')}
            </button>
          </>
        )}
        {translation && !isDirty && (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={deleting}
            className="p-0.5 text-muted-foreground hover:text-destructive transition-colors"
            title={t('translation_row.delete_aria')}
          >
            {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
          </button>
        )}
      </div>
      {aliasTags !== null ? (
        <AliasTagsInput
          tags={aliasTags}
          onChange={(next) => setValue(JSON.stringify(next))}
          placeholder={t('translation_row.tags_add')}
        />
      ) : (
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={1}
          placeholder={translationHint || t('translation_row.placeholder', { lang: language })}
          className="w-full rounded border border-blue-500/20 bg-background px-2 py-1.5 text-xs focus:border-blue-500/40 focus:outline-none focus:ring-1 focus:ring-blue-500/30 resize-y"
        />
      )}
      {sourceOriginal != null && sourceOriginal !== '' && (
        <p className="text-[10px] text-muted-foreground">
          {t('modal.viewing_original', {
            lang: sourceOriginalLang ? getLanguageName(sourceOriginalLang) : '?',
          })}
          : {sourceOriginal}
        </p>
      )}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('translation_row.delete_title')}
        description={t('translation_row.delete_desc', { lang: language.toUpperCase() })}
        confirmLabel={t('translation_row.delete_confirm')}
        variant="destructive"
        loading={deleting}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}

/** Chip editor for a per-language alias set. Controlled by the row's `value` (a JSON
 *  array string); emits the next array, which the row serializes with JSON.stringify —
 *  the exact format the BE glossary_propose_aliases writer and composePerLanguageAliases
 *  reader expect. Mirrors AttrTagsCard's UX, but JSON- (not CSV-) serialized. */
function AliasTagsInput({
  tags, onChange, placeholder,
}: { tags: string[]; onChange: (next: string[]) => void; placeholder: string }) {
  const [input, setInput] = useState('');

  const addTag = () => {
    const trimmed = input.trim();
    if (trimmed && !tags.includes(trimmed)) onChange([...tags, trimmed]);
    setInput('');
  };
  const removeTag = (tag: string) => onChange(tags.filter((tg) => tg !== tag));

  return (
    <div className="flex flex-wrap gap-1.5 rounded border border-blue-500/20 bg-background p-2">
      {tags.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 rounded bg-blue-500/12 px-2 py-0.5 text-xs text-blue-300">
          {tag}
          <button
            type="button"
            onClick={() => removeTag(tag)}
            className="text-muted-foreground/50 hover:text-foreground transition-colors"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
        onBlur={addTag}
        placeholder={placeholder}
        className="min-w-[80px] flex-1 bg-transparent px-1 py-0.5 text-xs outline-none placeholder:text-muted-foreground/40"
      />
    </div>
  );
}

import { useState } from 'react';
import { Check, Loader2, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { ConfirmDialog } from '@/components/shared';
import type { Translation, Confidence } from '@/features/glossary/types';

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
  onChanged: (updated: Translation | null) => void;
}

export function AttrTranslationRow({
  bookId, entityId, attrValueId, language,
  translation, translationHint, onChanged,
}: AttrTranslationRowProps) {
  const { accessToken } = useAuth();
  const [value, setValue] = useState(translation?.value ?? '');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isDirty = value !== (translation?.value ?? '');
  const isEmpty = !value.trim();

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
        toast.success('Translation updated');
      } else {
        // Create new
        const created = await glossaryApi.createTranslation(
          bookId, entityId, attrValueId,
          { language_code: language, value, confidence: 'draft' },
          accessToken,
        );
        onChanged(created);
        toast.success('Translation created');
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
      toast.success('Translation deleted');
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
            aria-label="Translation confidence"
          >
            <option value="draft">Draft</option>
            <option value="verified">Verified</option>
            <option value="machine">Machine</option>
          </select>
        )}
        {translation?.translator && (
          <span className="text-[9px] text-muted-foreground">by {translation.translator}</span>
        )}
        <span className="flex-1" />
        {isDirty && (
          <>
            <button
              type="button"
              onClick={() => setValue(translation?.value ?? '')}
              className="p-0.5 text-muted-foreground hover:text-foreground transition-colors"
              title="Discard changes"
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
              Save
            </button>
          </>
        )}
        {translation && !isDirty && (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            disabled={deleting}
            className="p-0.5 text-muted-foreground hover:text-destructive transition-colors"
            title="Delete translation"
          >
            {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
          </button>
        )}
      </div>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={1}
        placeholder={translationHint || `${language} translation...`}
        className="w-full rounded border border-blue-500/20 bg-background px-2 py-1.5 text-xs focus:border-blue-500/40 focus:outline-none focus:ring-1 focus:ring-blue-500/30 resize-y"
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete translation?"
        description={`The ${language.toUpperCase()} translation for this attribute will be permanently deleted.`}
        confirmLabel="Delete"
        variant="destructive"
        loading={deleting}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}

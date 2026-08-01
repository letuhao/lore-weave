// Mark a passage as WRONG (atom-edit Phase D) — the author's half of the error-block loop.
//
// Lives in the selection bubble beside Rewrite/Expand/Describe, but it is deliberately NOT one of
// them: those ask the model to improve prose right now, this records that a specific passage is
// wrong and WHY, durably, so the co-writer can act on it in a later turn (and on another device).
// The note is the whole value — a mark with no note is just a highlight.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { Editor } from '@tiptap/react';

import {
  errorBlocksApi, selectionToSpan, type ErrorBlockKind,
} from '../errorBlocks';

const KINDS: ErrorBlockKind[] = [
  'continuity', 'fact', 'logic', 'voice', 'pacing', 'style', 'other',
];

export function MarkErrorBlockAction({
  editor, projectId, chapterId, token, onMarked,
}: {
  editor: Editor;
  projectId: string;
  chapterId: string | null;
  token: string | null;
  onMarked?: () => void;
}) {
  const { t } = useTranslation('composition');
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [kind, setKind] = useState<ErrorBlockKind>('continuity');
  const [saving, setSaving] = useState(false);

  if (!chapterId || !token) return null;

  const submit = async () => {
    // Re-read the selection at SUBMIT time, not when the form opened: the author may have
    // adjusted it while typing the note, and marking the stale span would record a complaint
    // about prose they were no longer pointing at.
    const span = selectionToSpan(editor);
    if (!span) {
      toast.error(t('mark.no_selection', {
        defaultValue: 'Select the passage that is wrong before marking it.',
      }));
      return;
    }
    if (!note.trim()) {
      toast.error(t('mark.note_required', {
        defaultValue: 'Say what is wrong — the note is what the co-writer acts on.',
      }));
      return;
    }
    setSaving(true);
    try {
      await errorBlocksApi.create(projectId, chapterId, {
        start_offset: span.start, end_offset: span.end,
        quote: span.quote, source_fingerprint: span.fingerprint,
        kind, note: note.trim(),
      }, token);
      toast.success(t('mark.saved', { defaultValue: 'Marked — the co-writer can see this.' }));
      setNote('');
      setOpen(false);
      onMarked?.();
    } catch (e) {
      const msg = (e as Error).message || '';
      // A duplicate is a 409 by design (the API refuses to pretend a write happened). Say what
      // actually occurred rather than a generic failure the author would retry pointlessly.
      toast.error(/409|duplicate/i.test(msg)
        ? t('mark.duplicate', { defaultValue: 'You already marked this passage with that note.' })
        : t('mark.failed', { defaultValue: 'Could not save the mark. Try again.' }));
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        data-testid="selection-mark-error"
        className="rounded border px-2 py-0.5 hover:border-rose-500 hover:text-rose-600"
        onClick={() => setOpen(true)}
      >
        ⚑ {t('mark.action', { defaultValue: 'Mark problem' })}
      </button>
    );
  }

  return (
    <div data-testid="mark-error-form" className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <select
          data-testid="mark-error-kind"
          aria-label={t('mark.kind', { defaultValue: 'What kind of problem' })}
          className="rounded border bg-background px-1 py-0.5"
          value={kind}
          onChange={(e) => setKind(e.target.value as ErrorBlockKind)}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>{t(`mark.kind_${k}`, { defaultValue: k })}</option>
          ))}
        </select>
        <input
          data-testid="mark-error-note"
          aria-label={t('mark.note', { defaultValue: "What's wrong with this passage" })}
          placeholder={t('mark.note_ph', { defaultValue: 'e.g. she died in chapter 3…' })}
          className="min-w-0 flex-1 rounded border bg-background px-1 py-0.5"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void submit(); }}
        />
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          data-testid="mark-error-save"
          className="rounded bg-rose-600 px-2 py-0.5 text-white disabled:opacity-50"
          disabled={saving}
          onClick={() => void submit()}
        >
          {t('mark.save', { defaultValue: 'Mark it' })}
        </button>
        <button
          type="button"
          data-testid="mark-error-cancel"
          className="rounded border px-2 py-0.5 text-muted-foreground"
          onClick={() => { setOpen(false); setNote(''); }}
        >
          {t('mark.cancel', { defaultValue: 'Cancel' })}
        </button>
      </div>
    </div>
  );
}

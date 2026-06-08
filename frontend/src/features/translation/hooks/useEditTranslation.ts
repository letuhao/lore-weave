import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { versionsApi, type ChapterTranslation } from '../api';

/**
 * M7c-2 — controller for human-editing a translation version.
 *
 * Saving creates a NEW version (`authored_by='human'`) via the M7c-1 endpoint;
 * the LLM-draft → human-edit diff is captured as learning gold server-side. The
 * hook owns all edit state (MVC); the viewer only renders.
 *
 * Format-aware: a `json` version edits Tiptap blocks (the editor emits the doc
 * via `onEditorUpdate`; we persist `doc.content`); a `text` version edits a
 * plain string. The edit is always saved in the SOURCE version's format so the
 * before/after gold stays homogeneous (D-TRANSL-VERSION-NUM-RACE note).
 */
export function useEditTranslation(
  chapterId: string,
  version: ChapterTranslation | null,
  onSaved: (saved: ChapterTranslation) => void,
) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('translation');
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draftText, setDraftText] = useState('');
  // The live Tiptap doc from onUpdate (json format only).
  const draftDoc = useRef<{ type: string; content: unknown[] } | null>(null);

  const isJson = version?.translated_body_format === 'json';

  function startEdit() {
    if (!version) return;
    draftDoc.current = isJson
      ? { type: 'doc', content: (version.translated_body_json ?? []) as unknown[] }
      : null;
    setDraftText(version.translated_body ?? '');
    setEditing(true);
  }

  function cancel() {
    setEditing(false);
  }

  /** The initial doc handed to <TiptapEditor> when entering edit mode (json). */
  function editorContent() {
    return draftDoc.current ?? { type: 'doc', content: [] };
  }

  function onEditorUpdate(json: unknown) {
    draftDoc.current = json as { type: string; content: unknown[] };
  }

  async function save() {
    if (!accessToken || !version) return;
    // review-impl: skip an unchanged text edit — don't create a junk version /
    // no-op gold row (before==after). Reliable for text (exact compare); json
    // no-ops are filterable downstream by change_magnitude=0 (a robust Tiptap
    // dirty-check is a follow-up — D-TRANSL-M7C2-DIRTY).
    if (!isJson && draftText === (version.translated_body ?? '')) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const payload = isJson
        ? {
            target_language: version.target_language,
            edited_from_version_id: version.id,
            translated_body_json: (draftDoc.current?.content ?? []) as unknown[],
            translated_body_format: 'json' as const,
          }
        : {
            target_language: version.target_language,
            edited_from_version_id: version.id,
            translated_body: draftText,
            translated_body_format: 'text' as const,
          };
      const saved = await versionsApi.saveEditedVersion(accessToken, chapterId, payload);
      toast.success(t('viewer.edit_saved'));
      setEditing(false);
      onSaved(saved);
    } catch (e) {
      toast.error(t('viewer.edit_save_failed', { error: (e as Error).message }));
    } finally {
      setSaving(false);
    }
  }

  return {
    editing, saving, isJson, draftText, setDraftText,
    startEdit, cancel, save, editorContent, onEditorUpdate,
  };
}

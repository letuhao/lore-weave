// The accept→editor handoff shared by the S1 compose-loop dock panels (scene-compose + chapter-
// assemble). In the legacy page the loop was co-mounted with the Tiptap editor and inserted
// straight in; in the studio dock the editor is a SEPARATE panel, so accepted prose is written
// through the module-singleton editorBridge the EditorPanel registers.
//
// Two guards, because the compose/assemble views clear their draft UNCONDITIONALLY right after
// onAccept returns (there is no "accept again" — the ghost/preview is gone):
//   1. no editor open for this chapter  → focus THIS chapter (opens the editor on it) + tell the
//      writer to Generate again — never a false "accept again" the cleared draft can't honor.
//   2. editor open on a DIFFERENT chapter → refuse; inserting this chapter's draft into another
//      open manuscript would corrupt it. Both panels follow the same bus activeChapterId so they
//      normally agree, but a floated/separately-opened editor can drift — guard it explicitly.
import { useCallback } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { getEditorTarget } from '@/features/chat/context/editorBridge';
import { useStudioHost } from '../host/StudioHostProvider';

export function useAcceptIntoEditor(chapterId: string | null) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  return useCallback((text: string, meta?: { model?: string }) => {
    if (!chapterId) return;
    const target = getEditorTarget();
    if (!target?.applyProposedEdit || target.chapterId !== chapterId) {
      host.focusManuscriptUnit(chapterId);
      toast.info(t('sceneCompose.openedEditor', {
        defaultValue: 'Opened the Editor on this chapter — Generate again to insert the draft here.',
      }));
      return;
    }
    const ok = target.applyProposedEdit({
      operation: 'insert_at_cursor',
      text,
      provenance: { source: 'ai', status: 'unreviewed', model: meta?.model ?? null, ts: new Date().toISOString() },
    });
    if (ok) {
      toast.success(t('sceneCompose.inserted', { defaultValue: 'Accepted into the manuscript.' }));
    } else {
      toast.error(t('sceneCompose.insertFailed', {
        defaultValue: 'Could not insert — click into the chapter text in the Editor, then Accept again.',
      }));
    }
  }, [chapterId, host, t]);
}

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

/** Returns TRUE only when the prose actually landed in the editor. The caller (ComposeView /
 *  ChapterAssembleView) clears its draft ONLY on true — so a failed accept (no editor open on this
 *  chapter, or a rejected insert) never loses the draft (esp. a whole generated chapter). */
export function useAcceptIntoEditor(chapterId: string | null): (text: string, meta?: { model?: string }) => boolean {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  return useCallback((text: string, meta?: { model?: string }): boolean => {
    if (!chapterId) return false;
    const target = getEditorTarget();
    if (!target?.applyProposedEdit || target.chapterId !== chapterId) {
      host.focusManuscriptUnit(chapterId); // open the editor on THIS chapter so the retry lands
      toast.info(t('sceneCompose.openedEditor', {
        defaultValue: 'Opened the Editor on this chapter — your draft is kept; Accept again to insert it.',
      }));
      return false; // draft preserved — the caller must NOT clear it
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
    return ok;
  }, [chapterId, host, t]);
}
